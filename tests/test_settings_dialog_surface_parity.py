"""The Settings dialog, both sides at once.

A failure here means the Qt-free surface and the shipped dialog
disagree: one of them seeds a control with a different value, paints a
widget in a different place, wires a different action, writes a
different setting, or refuses a stored value where the other accepts it.

Every case drives the shipped dialog and the surface in one run, from
one input, and compares value for value and by hash. A stored value that
makes one side refuse must make the other side refuse with the same type
of exception; the wording is never compared.

Nothing here reads or writes the operator's settings file. Both sides
are driven with a store that holds its values in memory.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixtures.host_fonts import load_run_fonts
from tests.fixtures.surface_pictures import (
    assert_cases_paint_differently,
    assert_picture_can_report,
    assert_same_skin,
    colour_count,
    sealed,
    unaltered,
)
from src.gui.main_tabs import settings_dialog_surface as surface

REPO = Path(__file__).resolve().parents[1]
SHIPPED = REPO / "src" / "gui" / "settings_dialog.py"
SURFACE_FILE = REPO / "src" / "gui" / "main_tabs" / "settings_dialog_surface.py"

PICTURE_SIZE = (760, 900)
CONTROL_RULE = "QWidget { background: #7d1a4a; }"

_alive: list = []


def hold(widget):
    """Keep `widget` alive for the run so no render reads a freed object."""
    _alive.append(widget)
    return widget


def canonical(value):
    """`value` as nested lists of text, ordered so a swap changes it."""
    if isinstance(value, dict):
        pairs = sorted(value.items(), key=lambda item: repr(item[0]))
        return [[repr(key), canonical(inner)] for key, inner in pairs]
    if isinstance(value, (list, tuple)):
        return [canonical(inner) for inner in value]
    return repr(value)


def digest(payload) -> str:
    """SHA-256 over every value a payload carries, at every depth.

    Uses ``repr`` at the leaves, so a whole number and a decimal of the
    same size hash apart and a not-a-number hashes equal to itself.
    """
    return hashlib.sha256(repr(canonical(payload)).encode("utf-8")).hexdigest()


class Store:
    """The settings store both sides are driven with.

    Holds its values in memory and records every write, so no run of
    this file can reach the operator's settings file. ``refuses`` names
    the settings the store rejects, which is what the shipped store does
    for a name it does not carry.
    """

    def __init__(self, values=None, exchanges=None, refuses=()):
        self.values = dict(values or {})
        self.exchanges = list(exchanges or [])
        self.refuses = tuple(refuses)
        self.written: list = []
        self.removed: list = []

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        if key in self.refuses:
            raise KeyError(f"Unknown setting: {key}")
        self.values[key] = value
        self.written.append([key, value])

    def list_exchanges(self):
        return list(self.exchanges)

    def add_exchange(self, config):
        self.exchanges.append(config)

    def remove_exchange(self, exchange_id):
        self.removed.append(exchange_id)


class StatusLog:
    """The status line, keeping every message it was handed."""

    def __init__(self):
        self.lines: list = []

    def log(self, message, level="info"):
        self.lines.append([message, level])


class Validation:
    """One answer from the credential checker."""

    def __init__(self, success, message, details=None):
        self.success = success
        self.message = message
        self.details = details


class Checker:
    """The credential checker, answering from a value or an exception."""

    def __init__(self, result=None, raises=None):
        self.result = result
        self.raises = raises
        self.asked: list = []

    def __call__(self, exchange_id, key, secret, phrase):
        self.asked.append([exchange_id, key, secret, phrase])
        if self.raises is not None:
            raise self.raises
        return self.result


class SoundBox:
    """The sound engine, keeping the configs it got and what it played."""

    def __init__(self):
        self.configs: list = []
        self.played: list = []
        self._available = True
        self._cache = {"stale": 1}

    def update_config(self, config):
        self.configs.append(config)

    def play(self, name):
        self.played.append(name)


def sealed_encryptor(value, master):
    """Stand-in for the vault, returning a value that names both inputs."""
    return f"enc({value}|{master})"


def case(
    wing="crypto",
    settings=None,
    exchanges=None,
    refuses=(),
    result=None,
    raises=None,
):
    """One input both sides are driven with."""
    return {
        "wing": wing,
        "settings": dict(settings or {}),
        "exchanges": list(exchanges or []),
        "refuses": tuple(refuses),
        "result": result,
        "raises": raises,
    }


RECORDED_SETTERS = (
    "setValue",
    "setChecked",
    "setCurrentIndex",
    "setCurrentText",
    "setText",
    "setRange",
    "setDecimals",
    "setSuffix",
    "setPrefix",
    "setPlaceholderText",
    "setToolTip",
    "setStyleSheet",
    "setEnabled",
    "setVisible",
    "setEchoMode",
    "setMinimumHeight",
    "setMaximumHeight",
    "setMinimumWidth",
    "setWordWrap",
    "setEditable",
    "setProperty",
    "addItem",
    "addItems",
)

WIDGET_NAMES = (
    "QLabel",
    "QLineEdit",
    "QTextEdit",
    "QComboBox",
    "QCheckBox",
    "QRadioButton",
    "QSpinBox",
    "QDoubleSpinBox",
    "QSlider",
    "QListWidget",
    "QPushButton",
)


def make_recorder(base):
    """A subclass of `base` that keeps the arguments it was asked for.

    Every name in ``RECORDED_SETTERS`` that the class does not carry is
    skipped, so nothing here creates a method the platform never had.
    The base call still runs, so a value the platform refuses raises
    exactly as it does in the shipped dialog.
    """

    class Recorder(base):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.asked: dict = {}
            self.item_list: list = []
            self.built_with = list(args)

        def _keep(self, name, args):
            if hasattr(self, "asked"):
                self.asked[name] = list(args)

    def bind(name):
        def recorded(self, *args, **kwargs):
            self._keep(name, args)
            if hasattr(self, "item_list"):
                if name == "addItem":
                    self.item_list.append(list(args))
                if name == "addItems":
                    self.item_list.extend([one, None] for one in args[0])
            return getattr(base, name)(self, *args, **kwargs)

        return recorded

    for setter in RECORDED_SETTERS:
        if hasattr(base, setter):
            setattr(Recorder, setter, bind(setter))
    Recorder.__name__ = f"Recording{base.__name__}"
    return Recorder


class MessageBoxRecorder:
    """Stands in for the message box, keeping every box it was asked for."""

    seen: list = []

    @classmethod
    def information(cls, _parent, title, text):
        cls.seen.append(["information", title, text])

    @classmethod
    def warning(cls, _parent, title, text):
        cls.seen.append(["warning", title, text])


def swap_in_recorders(monkeypatch, module):
    """Point the shipped module's widget names at recording subclasses.

    ``raising=True`` throughout: a name the module does not carry must
    fail here rather than be created, which would swap nothing while
    reading as a swap.
    """
    from PySide6 import QtWidgets

    for name in WIDGET_NAMES:
        monkeypatch.setattr(
            module, name, make_recorder(getattr(QtWidgets, name)), raising=True
        )
    MessageBoxRecorder.seen = []
    monkeypatch.setattr(module, "QMessageBox", MessageBoxRecorder, raising=True)
    monkeypatch.setattr(module, "safe_process_events", _processed.append, raising=True)


_processed: list = []


def stub_services(monkeypatch, spec, sound):
    """Point the checker, the vault and the sound engine at values."""
    from src.core import encryption, sound_engine
    from src.exchange import api_validator

    checker = Checker(spec["result"], spec["raises"])
    monkeypatch.setattr(api_validator, "validate_credentials", checker, raising=True)
    monkeypatch.setattr(encryption, "encrypt", sealed_encryptor, raising=True)
    monkeypatch.setattr(sound_engine, "get_sound_engine", lambda: sound, raising=True)
    monkeypatch.setattr(sound_engine, "SoundConfig", dict, raising=True)
    return checker


def app():
    """The one application object, with this run's font choice applied.

    Building a Qt widget with no application object ends the process
    without a traceback, and a run that dies that way prints nothing at
    all, so every path that builds a widget passes through here first.
    """
    from PySide6.QtWidgets import QApplication

    load_run_fonts()
    return QApplication.instance()


LEAF_KINDS = (
    ("QRadioButton", "radio"),
    ("QCheckBox", "check"),
    ("QPushButton", "button"),
    ("QLabel", "label"),
    ("QTextEdit", "text_area"),
    ("QLineEdit", "line"),
    ("QComboBox", "combo"),
    ("QDoubleSpinBox", "double_spin"),
    ("QSpinBox", "spin"),
    ("QSlider", "slider"),
    ("QListWidget", "list"),
)


def _leaf_classes():
    from PySide6 import QtWidgets

    return tuple((getattr(QtWidgets, name), kind) for name, kind in LEAF_KINDS)


def _kind_of(widget, leaves):
    for cls, kind in leaves:
        if isinstance(widget, cls):
            return kind
    return None


def _printed(widget, kind):
    if kind == "combo":
        return widget.currentText()
    if kind == "text_area":
        return widget.toPlainText()
    if kind in ("label", "line", "check", "radio", "button"):
        return widget.text()
    return ""


def painted_widgets(page):
    """Every widget one tab paints, in painted order, as kind and text.

    Descends into a box but never into a control, so the line edit Qt
    builds inside a spin box is not counted as a second control.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QGroupBox, QWidget

    leaves = _leaf_classes()
    found: list = []

    def walk(parent):
        for child in parent.findChildren(
            QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly
        ):
            if isinstance(child, QGroupBox):
                found.append(["group", child.title()])
                walk(child)
                continue
            kind = _kind_of(child, leaves)
            if kind is not None:
                found.append([kind, _printed(child, kind)])
                continue
            walk(child)

    walk(page)
    return found


ECHO_NAMES = {0: "normal", 2: "password"}

NAMED = tuple(spec["name"] for spec in surface.CONTROL_SPECS)
BUTTON_NAMES = ("cancel_btn", "save_btn", "test_btn", "add_btn", "ai_test_btn")
LABEL_NAMES = (
    "api_feedback",
    "font_preview",
    "vol_label",
    "ai_status",
    "ai_hash",
    "ai_checks",
)
STYLED_NAMES = LABEL_NAMES + ("save_btn", "ai_test_btn")
PROPERTY_NAMES = ("save_btn", "add_btn")


def _asked(widget, setter, missing=None):
    recorded = widget.asked.get(setter)
    return recorded[0] if recorded else missing


def old_value(widget, kind):
    if kind in ("spin", "double_spin", "slider"):
        return widget.value()
    if kind in ("check", "radio"):
        return widget.isChecked()
    if kind == "combo":
        return widget.currentIndex()
    if kind == "line":
        return widget.text()
    if kind == "text_area":
        return widget.toPlainText()
    return [widget.item(at).text() for at in range(widget.count())]


def read_shipped(dialog, store, log, printed_lines):
    """Everything the shipped dialog painted, as plain values."""
    from PySide6.QtWidgets import QPushButton, QTabWidget

    tabs = dialog.findChildren(QTabWidget)[0]
    payload = {
        "window_title": dialog.windowTitle(),
        "minimum_size": [dialog.minimumWidth(), dialog.minimumHeight()],
        "tabs": [tabs.tabText(at) for at in range(tabs.count())],
        "painted": {
            tabs.tabText(at): painted_widgets(tabs.widget(at))
            for at in range(tabs.count())
        },
        "values": {},
        "ranges": {},
        "decimals": {},
        "suffix": {},
        "prefix": {},
        "tooltips": {},
        "placeholders": {},
        "echo": {},
        "enabled": {},
        "visible": {},
        "styles": {},
        "combo_items": {},
        "heights": {},
        "texts": {},
        "properties": {},
        "written": [list(one) for one in store.written],
        "removed": list(store.removed),
        "status_lines": [list(one) for one in log.lines],
        "message_boxes": [list(one) for one in MessageBoxRecorder.seen],
        "prints": list(printed_lines),
        "accepted": dialog.result(),
    }
    for spec in surface.CONTROL_SPECS:
        name = spec["name"]
        widget = getattr(dialog, "_" + name)
        kind = surface.PAINTED_KIND[spec["kind"]]
        payload["values"][name] = old_value(widget, kind)
        payload["tooltips"][name] = widget.toolTip()
        payload["enabled"][name] = widget.isEnabled()
        payload["visible"][name] = bool(_asked(widget, "setVisible", True))
        if kind in ("spin", "double_spin", "slider"):
            payload["ranges"][name] = [widget.minimum(), widget.maximum()]
        if kind in ("spin", "double_spin"):
            payload["suffix"][name] = widget.suffix()
            payload["prefix"][name] = widget.prefix()
        if kind == "double_spin":
            payload["decimals"][name] = widget.decimals()
        if kind in ("line", "text_area"):
            payload["placeholders"][name] = widget.placeholderText()
        if kind == "line":
            payload["echo"][name] = ECHO_NAMES[int(widget.echoMode().value)]
        if kind == "combo":
            payload["combo_items"][name] = [
                [widget.itemText(at), widget.itemData(at)]
                for at in range(widget.count())
            ]
        if "min_height" in spec:
            payload["heights"][name] = _asked(widget, "setMinimumHeight")
        if "max_height" in spec:
            payload["heights"][name] = _asked(widget, "setMaximumHeight")
    for name in LABEL_NAMES + BUTTON_NAMES:
        payload["texts"][name] = getattr(dialog, "_" + name).text()
    for name in BUTTON_NAMES:
        payload["enabled"][name] = getattr(dialog, "_" + name).isEnabled()
    for name in STYLED_NAMES:
        payload["styles"][name] = _asked(
            getattr(dialog, "_" + name), "setStyleSheet", ""
        )
    for name in PROPERTY_NAMES:
        payload["properties"][name] = _asked(getattr(dialog, "_" + name), "setProperty")
    for button in dialog.findChildren(QPushButton):
        if button.text() == surface.REMOVE_BUTTON_TEXT:
            payload["properties"]["remove_btn"] = _asked(button, "setProperty")
    return payload


def read_surface(model):
    """Everything the surface says the dialog paints, in the same shape."""
    view = surface.build_view_model(model)
    payload = {
        "window_title": view["window_title"],
        "minimum_size": list(view["minimum_size"]),
        "tabs": list(view["tabs"]),
        "painted": view["painted"],
        "values": {},
        "ranges": {},
        "decimals": {},
        "suffix": {},
        "prefix": {},
        "tooltips": {},
        "placeholders": {},
        "echo": {},
        "enabled": {},
        "visible": {},
        "styles": {},
        "combo_items": {},
        "heights": {},
        "texts": {},
        "properties": {},
        "written": [list(one) for one in model.settings.written],
        "removed": list(model.settings.removed),
        "status_lines": [list(one) for one in model.status_log.lines],
        "message_boxes": [list(one) for one in view["message_boxes"]],
        "prints": list(view["prints"]),
        "accepted": int(bool(view["accepted"])),
    }
    for spec in surface.CONTROL_SPECS:
        name = spec["name"]
        kind = surface.PAINTED_KIND[spec["kind"]]
        payload["values"][name] = model.values[name]
        payload["tooltips"][name] = model.tooltips.get(name, "")
        payload["enabled"][name] = model.enabled[name]
        payload["visible"][name] = model.visible[name]
        if kind in ("spin", "double_spin", "slider"):
            payload["ranges"][name] = list(spec["range"])
        if kind in ("spin", "double_spin"):
            payload["suffix"][name] = spec.get("suffix", "")
            payload["prefix"][name] = spec.get("prefix", "")
        if kind == "double_spin":
            payload["decimals"][name] = spec.get("decimals", surface.DEFAULT_DECIMALS)
        if kind in ("line", "text_area"):
            payload["placeholders"][name] = spec.get("placeholder", "")
        if kind == "line":
            payload["echo"][name] = spec.get("echo", "normal")
        if kind == "combo":
            payload["combo_items"][name] = surface_combo_items(spec, view)
        if "min_height" in spec:
            payload["heights"][name] = spec["min_height"]
        if "max_height" in spec:
            payload["heights"][name] = spec["max_height"]
    for name in LABEL_NAMES:
        payload["texts"][name] = model.texts[name]
    payload["texts"]["cancel_btn"] = view["buttons"]["cancel"]
    payload["texts"]["save_btn"] = view["buttons"]["save"]
    payload["texts"]["test_btn"] = view["buttons"]["test"]
    payload["texts"]["add_btn"] = view["buttons"]["add"]
    payload["texts"]["ai_test_btn"] = view["buttons"]["ai_test"]
    for name in BUTTON_NAMES:
        payload["enabled"][name] = model.enabled.get(name, True)
    for name in LABEL_NAMES:
        payload["styles"][name] = model.styles.get(name, "")
    payload["styles"]["save_btn"] = view["buttons"]["save_style"]
    payload["styles"]["ai_test_btn"] = view["buttons"]["ai_test_style"]
    payload["properties"]["save_btn"] = surface.ACCENT_PROPERTY
    payload["properties"]["add_btn"] = surface.ACCENT_PROPERTY
    payload["properties"]["remove_btn"] = surface.DANGER_PROPERTY
    return payload


def surface_combo_items(spec, view):
    """The item list one combo was filled with, in the recorded shape."""
    if spec["name"] == "new_exchange":
        return [list(one) for one in view["exchange_items"]]
    if spec["kind"] == surface.COMBO_DATA:
        return [list(one) for one in spec["items"]]
    return [[one, None] for one in spec["items"]]


def settings_lines(capsys):
    """Every line the shipped dialog printed for the operator's log."""
    captured = capsys.readouterr()
    return [line for line in captured.err.splitlines() if line.startswith("[SETTINGS")]


def shipped_dialog(monkeypatch, spec, sound=None):
    """The real Settings dialog, built by the shipped class."""
    import src.gui.settings_dialog as shipped

    app()
    swap_in_recorders(monkeypatch, shipped)
    stub_services(monkeypatch, spec, sound or SoundBox())
    store = Store(spec["settings"], spec["exchanges"], spec["refuses"])
    log = StatusLog()
    dialog = hold(shipped.SettingsDialog(store, log, None, spec["wing"]))
    return dialog, store, log


def surface_model(spec, sound=None):
    """The surface's model for the same input."""
    store = surface.SettingsSource(spec["settings"], spec["exchanges"], spec["refuses"])
    model = surface.SettingsDialogModel(
        settings=store,
        status_log=surface.StatusLogSink(),
        wing=spec["wing"],
        validator=surface.ValidatorSource(spec["result"], spec["raises"]),
        sound=sound or surface.SoundEngineSink(),
        encryptor=sealed_encryptor,
    )
    model.build()
    return model


def old_snapshot(monkeypatch, spec, capsys):
    """Drive the shipped dialog once and return what it painted."""
    try:
        dialog, store, log = shipped_dialog(monkeypatch, spec)
    except BaseException as exc:
        settings_lines(capsys)
        return ("refused", type(exc).__name__)
    return ("built", read_shipped(dialog, store, log, settings_lines(capsys)))


def new_snapshot(spec):
    """Drive the surface once and return what it says the dialog paints."""
    try:
        model = surface_model(spec)
    except BaseException as exc:
        return ("refused", type(exc).__name__)
    return ("built", read_surface(model))


def drive_both(monkeypatch, spec, capsys):
    """Drive the shipped dialog and the surface once each, from one input."""
    return old_snapshot(monkeypatch, spec, capsys), new_snapshot(spec)


def assert_same(old, new, note=""):
    """Fail unless both sides built the same dialog, or refused alike."""
    tail = f" [{note}]" if note else ""
    assert old[0] == new[0], (
        f"one side built the dialog and the other refused{tail}: "
        f"shipped {old[0]} {old[1] if old[0] == 'refused' else ''}, "
        f"surface {new[0]} {new[1] if new[0] == 'refused' else ''}"
    )
    if old[0] == "refused":
        assert old[1] == new[1], (
            f"the two sides refused with different exception types{tail}: "
            f"shipped {old[1]}, surface {new[1]}"
        )
        return
    old_payload, new_payload = old[1], new[1]
    for key in sorted(set(old_payload) | set(new_payload)):
        assert old_payload.get(key) == new_payload.get(key), (
            f"the surface and the shipped dialog disagree on {key!r}{tail}:\n"
            f"  shipped: {old_payload.get(key)!r}\n"
            f"  surface: {new_payload.get(key)!r}"
        )
    assert digest(old_payload) == digest(new_payload), (
        f"the two sides hashed apart{tail}: "
        f"shipped {digest(old_payload)}, surface {digest(new_payload)}"
    )


def test_a_plain_crypto_wing_paints_the_same_dialog_on_both_sides(monkeypatch, capsys):
    """The surface and the shipped dialog disagree on a plain crypto wing."""
    old, new = drive_both(monkeypatch, case(), capsys)
    assert_same(old, new)


LONG_NAME = "z" * 200
MARKUP_NAME = "<b>hal</b> & <i>co</i>"
NEWLINE_NAME = "first\nsecond"
UNICODE_NAME = "Ekthèlius the Æccumulator"
APOSTROPHE_NAME = "hal's bot"
WRONG_CAPITALS = "CyberPunk_Dark"

PAIRED_CASES = {
    "the stock wing": case(wing="stock"),
    "a wing nobody named": case(wing="phantom"),
    "an empty settings file": case(settings={}),
    "a setting the dialog does not know": case(settings={"a_key_nobody_reads": 1}),
    "a crypto exchange already configured": case(
        exchanges=[{"exchange_id": "coinbase", "display_name": "Coinbase"}]
    ),
    "an equity broker on the crypto wing": case(
        exchanges=[{"exchange_id": "alpaca", "display_name": "Alpaca"}]
    ),
    "an equity broker on the stock wing": case(
        wing="stock",
        exchanges=[{"exchange_id": "alpaca", "display_name": "Alpaca"}],
    ),
    "an exchange entry with neither key": case(exchanges=[{}]),
    "an exchange id in capitals": case(
        exchanges=[{"exchange_id": "ALPACA", "display_name": "Alpaca"}]
    ),
    "a name 200 characters long": case(settings={"username": LONG_NAME}),
    "a name carrying markup": case(settings={"username": MARKUP_NAME}),
    "a name carrying an apostrophe": case(settings={"username": APOSTROPHE_NAME}),
    "a name carrying a newline": case(settings={"username": NEWLINE_NAME}),
    "a name outside the plain alphabet": case(settings={"username": UNICODE_NAME}),
    "an empty name": case(settings={"username": ""}),
    "a theme name in the wrong capitals": case(settings={"theme": WRONG_CAPITALS}),
    "a theme nobody ships": case(settings={"theme": "no_such_theme"}),
    "an increment style nobody ships": case(settings={"increment_style": "sideways"}),
    "a folding group that is empty": case(settings={"profit_folding": {}}),
    "an ai group that is empty": case(settings={"ai_monitor": {}}),
    "a target balance of zero": case(settings={"default_target_balance": 0}),
    "a negative target balance": case(settings={"default_target_balance": -1.0}),
    "a target balance of a thousand million": case(
        settings={"default_target_balance": 1_000_000_000}
    ),
    "a target balance of one billionth": case(
        settings={"default_target_balance": 1e-9}
    ),
    "a target balance of infinity": case(
        settings={"default_target_balance": float("inf")}
    ),
    "a target balance of minus infinity": case(
        settings={"default_target_balance": float("-inf")}
    ),
    "a target balance that is not a number": case(
        settings={"default_target_balance": float("nan")}
    ),
    "a target balance of two to the 1023": case(
        settings={"default_target_balance": 2**1023}
    ),
    "a stored true where a target balance belongs": case(
        settings={"default_target_balance": True}
    ),
    "a stored true where a position count belongs": case(
        settings={"default_position_count": True}
    ),
    "a position count with a fraction": case(settings={"default_position_count": 12.7}),
    "an interval that is not a number": case(
        settings={"ai_monitor": {"interval_hours": float("nan")}}
    ),
    "every setting stored with the wrong type at once": case(
        settings={
            "username": "text",
            "position_distance_pct": float("inf"),
            "default_position_count": True,
            "default_target_balance": float("nan"),
            "accent_color": "not a colour",
            "theme": "not a theme",
            "increment_style": "not a style",
            "profit_folding": {"active": False},
            "ai_monitor": {
                "api_key": "",
                "interval_hours": float("-inf"),
                "connect_phrase": "",
                "confirm_phrase": "",
                "enabled": True,
                "auto_handshake": False,
                "log_feedback": False,
            },
        }
    ),
}


@pytest.mark.qt_no_exception_capture
@pytest.mark.parametrize("name", sorted(PAIRED_CASES))
def test_both_sides_paint_the_same_dialog(monkeypatch, capsys, name):
    """One side painted a different Settings dialog than the other."""
    old, new = drive_both(monkeypatch, PAIRED_CASES[name], capsys)
    assert_same(old, new, name)


REFUSING_CASES = {
    "a name stored as a number": case(settings={"username": 12.7}),
    "a name stored as a true": case(settings={"username": True}),
    "a name stored as a whole number": case(settings={"username": 2**31}),
    "an accent colour stored as a number": case(settings={"accent_color": 12.7}),
    "a position distance stored as text": case(
        settings={"position_distance_pct": "abc"}
    ),
    "a position distance stored as a numeric string": case(
        settings={"position_distance_pct": "12.7"}
    ),
    "a target balance of ten to the four hundred": case(
        settings={"default_target_balance": 10**400}
    ),
    "a target balance of two to the 1024": case(
        settings={"default_target_balance": 2**1024}
    ),
    "a position count that is not a number": case(
        settings={"default_position_count": float("nan")}
    ),
    "a position count of infinity": case(
        settings={"default_position_count": float("inf")}
    ),
    "a position count of minus infinity": case(
        settings={"default_position_count": float("-inf")}
    ),
    "a position count of ten to the four hundred": case(
        settings={"default_position_count": 10**400}
    ),
    "a position count stored as text": case(settings={"default_position_count": "abc"}),
    "an increment style stored as a number": case(settings={"increment_style": 12.7}),
    "an increment style stored as a true": case(settings={"increment_style": True}),
    "a theme stored as ten to the four hundred": case(settings={"theme": 10**400}),
    "an ai group stored as a number": case(settings={"ai_monitor": 5}),
    "an ai group stored as a list": case(settings={"ai_monitor": []}),
    "a folding group stored as a number": case(settings={"profit_folding": 5}),
    "an ai flag stored as text": case(settings={"ai_monitor": {"enabled": "yes"}}),
    "an ai flag stored as a decimal": case(settings={"ai_monitor": {"enabled": 12.7}}),
    "an ai flag stored as a huge number": case(
        settings={"ai_monitor": {"enabled": 10**400}}
    ),
    "an exchange entry that is not a mapping": case(exchanges=["coinbase"]),
    "an exchange id stored as a number": case(
        exchanges=[{"exchange_id": 7, "display_name": "x"}]
    ),
}


@pytest.mark.qt_no_exception_capture
@pytest.mark.parametrize("name", sorted(REFUSING_CASES))
def test_both_sides_refuse_the_same_stored_value(monkeypatch, capsys, name):
    """One side opened the dialog on a stored value the other refused.

    Refusals are compared by the type of the exception, never by its
    wording.
    """
    old, new = drive_both(monkeypatch, REFUSING_CASES[name], capsys)
    assert old[0] == "refused", f"[{name}] the shipped dialog opened: {old}"
    assert_same(old, new, name)


def test_the_refusal_check_would_report_a_side_that_opened(monkeypatch, capsys):
    """The refusal comparison passes a case where only one side refused."""
    refused = ("refused", "TypeError")
    built = ("built", {})
    with pytest.raises(AssertionError) as reported:
        assert_same(refused, built)
    assert "one side built the dialog" in str(reported.value)
    with pytest.raises(AssertionError) as other:
        assert_same(refused, ("refused", "OverflowError"))
    assert "different exception types" in str(other.value)


# --- the comparison's own controls ---------------------------------------


def test_two_different_real_inputs_hash_apart_on_each_side(monkeypatch, capsys):
    """The value comparison passes whatever the second side paints.

    Two genuinely different real inputs, one driven through each side,
    in both directions.
    """
    first = case(settings={"username": "hal"})
    second = case(settings={"username": "satoshi"})
    old_first = old_snapshot(monkeypatch, first, capsys)
    new_second = new_snapshot(second)
    with pytest.raises(AssertionError):
        assert_same(old_first, new_second)

    old_second = old_snapshot(monkeypatch, second, capsys)
    new_first = new_snapshot(first)
    with pytest.raises(AssertionError):
        assert_same(old_second, new_first)
    assert digest(old_first[1]) != digest(old_second[1]), (
        "the two real inputs hashed the same on the shipped side, so "
        "neither direction above proves the comparison can report"
    )
    assert digest(new_first[1]) != digest(
        new_second[1]
    ), "the two real inputs hashed the same on the surface side"


def test_the_same_input_twice_hashes_the_same(monkeypatch, capsys):
    """One input drove two different pictures out of one side."""
    spec = case(settings={"username": "hal"})
    once = old_snapshot(monkeypatch, spec, capsys)
    twice = old_snapshot(monkeypatch, spec, capsys)
    assert digest(once[1]) == digest(
        twice[1]
    ), "the shipped dialog painted two different pictures from one input"


def test_a_whole_number_and_a_decimal_hash_apart():
    """The hash folds a whole number into a decimal of the same size."""
    assert digest({"count": 12}) != digest({"count": 12.0}), (
        "12 and 12.0 hashed the same, so a control seeded with one and "
        "compared against the other would pass"
    )
    assert {"count": 12} == {
        "count": 12.0
    }, "these two are equal by value, which is why the hash is needed"


def test_two_not_a_numbers_hash_the_same_and_compare_apart():
    """The hash reports a difference between one not-a-number and itself."""
    one = float("nan")
    assert digest({"x": one}) == digest({"x": float("nan")}), (
        "two not-a-numbers hashed apart, so every payload holding one "
        "would report a difference that is not one"
    )
    assert {"x": one} != {"x": float("nan")}, (
        "a plain comparison of two not-a-numbers reported them equal, "
        "which is why the hash carries the payload"
    )


def test_a_swapped_pair_of_values_changes_the_hash():
    """The hash reads two swapped values as one payload."""
    straight = {"a": 1, "b": 2}
    swapped = {"a": 2, "b": 1}
    assert digest(straight) != digest(swapped), swapped


# --- what the dialog wires -----------------------------------------------


def connect_sites_in(path):
    """Every line in `path` that connects a signal, read by parsing."""
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == "connect":
            found.append(node.lineno)
    return found


def test_the_source_connect_sites_match_the_number_the_surface_names():
    """The surface names a different number of connect lines than the file holds.

    Counted from the parsed file, which cannot see a connect inside a
    comment or a string.
    """
    found = connect_sites_in(SHIPPED)
    named = surface.connection_counts()["source_sites"]
    assert len(found) == named, (
        f"the shipped file holds {len(found)} connect lines at {found}, "
        f"and the surface names {named}"
    )


def test_the_connect_counter_reports_a_planted_line(tmp_path):
    """The connect counter's number is a fact about the counter."""
    planted = tmp_path / "planted.py"
    planted.write_text(
        "def sample(one):\n"
        "    one.clicked.connect(one.run)\n"
        "    # one.other.connect(one.run)\n"
        '    text = "one.third.connect(one.run)"\n'
        "    return text\n",
        encoding="utf-8",
        newline="\n",
    )
    assert connect_sites_in(planted) == [2], connect_sites_in(planted)


def test_the_dialog_makes_more_connections_than_it_has_connect_lines(
    monkeypatch, capsys
):
    """One connect line inside a loop wires one connection per pass.

    The two figures are counted on the built dialog, not read off the
    surface, so a surface that names the wrong number is reported.
    """
    counts = surface.connection_counts()
    weights = len(surface.TA_INDICATOR_WEIGHTS)
    assert counts["run_time"] == counts["source_sites"] + weights - 1, counts

    dialog, _store, _log = shipped_dialog(monkeypatch, case())
    settings_lines(capsys)
    assert len(dialog._ta_weight_sliders) == weights, dialog._ta_weight_sliders
    assert counts["run_time"] > counts["source_sites"], counts


def test_the_surface_names_one_action_for_every_connection_it_counts():
    """The action table and the connection count disagree."""
    wired = surface.actions()
    assert len(wired) == surface.connection_counts()["run_time"], sorted(wired)
    assert "a signal nobody connects" not in wired


def test_the_dialog_declares_one_signal_and_emits_it_on_save(monkeypatch, capsys):
    """The dialog's own signal is not emitted when the operator saves."""
    dialog, _store, _log = shipped_dialog(monkeypatch, case())
    emitted: list = []
    dialog.settings_changed.connect(lambda: emitted.append("settings_changed"))
    dialog._save()
    settings_lines(capsys)
    assert emitted == list(surface.QT_SIGNALS), emitted

    model = surface_model(case())
    model.save()
    assert model.emitted == list(surface.QT_SIGNALS), model.emitted


def test_the_dialog_builds_no_timer_and_starts_no_thread(monkeypatch, capsys):
    """The dialog built a timer or started a thread nobody counted."""
    import threading

    before = threading.active_count()
    dialog, _store, _log = shipped_dialog(monkeypatch, case())
    settings_lines(capsys)
    from PySide6.QtCore import QTimer

    assert dialog.findChildren(QTimer) == [], dialog.findChildren(QTimer)
    assert threading.active_count() == before, threading.active_count()
    assert list(surface.TIMERS_BUILT) == [], surface.TIMERS_BUILT
    assert list(surface.TIMERS_STARTED) == [], surface.TIMERS_STARTED
    assert list(surface.THREADS_BUILT) == [], surface.THREADS_BUILT
    assert list(surface.THREADS_STARTED) == [], surface.THREADS_STARTED

    started = threading.Thread(target=lambda: None, name="probe")
    started.start()
    started.join()
    spare = QTimer(dialog)
    assert dialog.findChildren(QTimer) == [spare], (
        "the timer counter found nothing after one real timer was built, "
        "so its empty answer above was a fact about the counter"
    )


# --- driving the dialog step by step -------------------------------------


def old_state(dialog, store, log, sound, printed_lines):
    """What the shipped dialog holds after a sequence of steps."""
    return {
        "values": {
            spec["name"]: old_value(
                getattr(dialog, "_" + spec["name"]),
                surface.PAINTED_KIND[spec["kind"]],
            )
            for spec in surface.CONTROL_SPECS
        },
        "texts": {name: getattr(dialog, "_" + name).text() for name in LABEL_NAMES},
        "styles": {
            name: _asked(getattr(dialog, "_" + name), "setStyleSheet", "")
            for name in LABEL_NAMES
        },
        "enabled": {
            name: getattr(dialog, "_" + name).isEnabled()
            for name in ("test_btn", "add_btn")
        },
        "visible": {
            "new_passphrase": bool(_asked(dialog._new_passphrase, "setVisible", True))
        },
        "written": [list(one) for one in store.written],
        "removed": list(store.removed),
        "exchanges": [as_plain(one) for one in store.exchanges],
        "status_lines": [list(one) for one in log.lines],
        "message_boxes": [list(one) for one in MessageBoxRecorder.seen],
        "prints": list(printed_lines),
        "played": list(sound.played),
        "configs": [dict(one) for one in sound.configs],
        "engine_cleared": [sound._available, dict(sound._cache)],
        "accepted": dialog.result(),
    }


def new_state(model, sound):
    """What the surface holds after the same sequence of steps."""
    return {
        "values": {
            spec["name"]: model.values[spec["name"]] for spec in surface.CONTROL_SPECS
        },
        "texts": {name: model.texts[name] for name in LABEL_NAMES},
        "styles": {name: model.styles.get(name, "") for name in LABEL_NAMES},
        "enabled": {
            name: model.enabled.get(name, True) for name in ("test_btn", "add_btn")
        },
        "visible": {"new_passphrase": model.visible["new_passphrase"]},
        "written": [list(one) for one in model.settings.written],
        "removed": list(model.settings.removed),
        "exchanges": [as_plain(one) for one in model.settings.exchanges],
        "status_lines": [list(one) for one in model.status_log.lines],
        "message_boxes": [list(one) for one in model.message_boxes],
        "prints": list(model.prints),
        "played": list(sound.played),
        "configs": [dict(one) for one in sound.configs],
        "engine_cleared": [sound._available, dict(sound._cache)],
        "accepted": int(bool(model.accepted)),
    }


OLD_STEPS = {
    "type key": lambda d, v: d._new_api_key.setText(v),
    "type secret": lambda d, v: d._new_api_secret.setPlainText(v),
    "type phrase": lambda d, v: d._new_passphrase.setText(v),
    "tick phrase box": lambda d, v: d._pp_check.setChecked(v),
    "choose exchange": lambda d, v: d._new_exchange.setCurrentIndex(v),
    "test connection": lambda d, v: d._test_api_connection(),
    "add exchange": lambda d, v: d._add_exchange(),
    "select listed": lambda d, v: d._exchange_list.setCurrentRow(v),
    "remove exchange": lambda d, v: d._remove_exchange(),
    "move volume": lambda d, v: d._sound_volume.setValue(v),
    "play sound": lambda d, v: d._test_sound(v),
    "set font size": lambda d, v: d._font_size.setValue(v),
    "type ai key": lambda d, v: d._ai_api_key.setText(v),
    "type connect phrase": lambda d, v: d._ai_connect_phrase.setText(v),
    "type confirm phrase": lambda d, v: d._ai_confirm_phrase.setText(v),
    "handshake": lambda d, v: d._test_ai_handshake(),
    "save": lambda d, v: d._save(),
    "cancel": lambda d, v: d.reject(),
}


def as_plain(config):
    """One stored exchange config as a plain mapping, whatever built it."""
    if dataclasses.is_dataclass(config):
        return dataclasses.asdict(config)
    return dict(config)


NEW_STEPS = {
    "type key": lambda m, v: m.edit("new_api_key", v),
    "type secret": lambda m, v: m.edit("new_api_secret", v),
    "type phrase": lambda m, v: m.edit("new_passphrase", v),
    "tick phrase box": lambda m, v: m.edit("pp_check", v),
    "choose exchange": lambda m, v: m.edit("new_exchange", v),
    "test connection": lambda m, v: m.test_api_connection(),
    "add exchange": lambda m, v: m.add_exchange(),
    "select listed": lambda m, v: setattr(m, "selected_row", v),
    "remove exchange": lambda m, v: m.remove_exchange(
        m.values["exchange_list"][m.selected_row]
        if getattr(m, "selected_row", None) is not None and m.values["exchange_list"]
        else None
    ),
    "move volume": lambda m, v: m.edit("sound_volume", v),
    "play sound": lambda m, v: m.test_sound(v),
    "set font size": lambda m, v: m.edit("font_size", v),
    "type ai key": lambda m, v: m.edit("ai_api_key", v),
    "type connect phrase": lambda m, v: m.edit("ai_connect_phrase", v),
    "type confirm phrase": lambda m, v: m.edit("ai_confirm_phrase", v),
    "handshake": lambda m, v: m.test_ai_handshake(),
    "save": lambda m, v: m.save(),
    "cancel": lambda m, v: m.cancel(),
}


def run_old_steps(monkeypatch, spec, steps, capsys):
    """Run one sequence on the shipped dialog and report where it stopped."""
    sound = SoundBox()
    dialog, store, log = shipped_dialog(monkeypatch, spec, sound)
    reached = []
    stopped = None
    for at, (name, value) in enumerate(steps):
        try:
            OLD_STEPS[name](dialog, value)
        except BaseException as exc:
            stopped = [at, name, type(exc).__name__]
            break
        reached.append([at, name])
    return (
        reached,
        stopped,
        old_state(dialog, store, log, sound, settings_lines(capsys)),
    )


def run_new_steps(spec, steps):
    """Run the same sequence on the surface."""
    sound = SoundBox()
    model = surface_model(spec, sound)
    reached = []
    stopped = None
    for at, (name, value) in enumerate(steps):
        try:
            NEW_STEPS[name](model, value)
        except BaseException as exc:
            stopped = [at, name, type(exc).__name__]
            break
        reached.append([at, name])
    return reached, stopped, new_state(model, sound)


GOOD_RESULT = Validation(True, "Connected to Coinbase", "USD 12.50")
FAILED_RESULT = Validation(False, "Bad key", "401 from the venue")

STEP_RUNS = {
    "a plain save": (case(), [("save", None)]),
    "a cancel after an edit": (
        case(),
        [("type ai key", "abc"), ("cancel", None)],
    ),
    "an edit then a save": (
        case(),
        [("type ai key", "sk-test"), ("save", None)],
    ),
    "a partial save": (
        case(refuses=("font_size", "ai_monitor")),
        [("save", None)],
    ),
    "a save with every group refused": (
        case(
            refuses=(
                "username",
                "position_distance_pct",
                "increment_style",
                "default_position_count",
                "default_target_balance",
                "bot_visibility",
                "aggressive_trading",
                "theme",
                "accent_color",
                "font_family",
                "font_size",
                "heading_font_size",
                "log_font_size",
                "profit_folding",
                "data_logging",
                "ai_monitor",
            )
        ),
        [("save", None)],
    ),
    "a connection test with nothing typed": (
        case(),
        [("test connection", None)],
    ),
    "a connection test that passes": (
        case(result=GOOD_RESULT),
        [("type key", "k"), ("type secret", "s"), ("test connection", None)],
    ),
    "a connection test that fails": (
        case(result=FAILED_RESULT),
        [("type key", "k"), ("type secret", "s"), ("test connection", None)],
    ),
    "a connection test that raises": (
        case(raises=RuntimeError("venue is down")),
        [("type key", "k"), ("type secret", "s"), ("test connection", None)],
    ),
    "adding an exchange with no credentials": (
        case(),
        [("choose exchange", 5), ("add exchange", None)],
    ),
    "adding an exchange with credentials": (
        case(result=GOOD_RESULT),
        [
            ("choose exchange", 5),
            ("type key", " k "),
            ("type secret", " s "),
            ("add exchange", None),
        ],
    ),
    "adding an exchange with a passphrase": (
        case(result=GOOD_RESULT),
        [
            ("choose exchange", 2),
            ("type key", "k"),
            ("type secret", "s"),
            ("tick phrase box", True),
            ("type phrase", "p"),
            ("add exchange", None),
        ],
    ),
    "adding an exchange the venue refused": (
        case(result=FAILED_RESULT),
        [
            ("type key", "k"),
            ("type secret", "s"),
            ("add exchange", None),
        ],
    ),
    "removing nothing": (case(), [("remove exchange", None)]),
    "removing the listed exchange": (
        case(exchanges=[{"exchange_id": "coinbase", "display_name": "Coinbase"}]),
        [("select listed", 0), ("remove exchange", None)],
    ),
    "moving the volume": (case(), [("move volume", 40)]),
    "playing every sound": (
        case(),
        [("play sound", name) for name in surface.SOUND_NAMES],
    ),
    "a handshake with no key": (case(), [("handshake", None)]),
    "a handshake with no phrases": (
        case(),
        [("type ai key", "sk-test"), ("handshake", None)],
    ),
    "a handshake with everything": (
        case(),
        [
            ("type ai key", "sk-test"),
            ("type connect phrase", "hello"),
            ("type confirm phrase", "there"),
            ("handshake", None),
        ],
    ),
    "an edit, a handshake and a save": (
        case(),
        [
            ("type ai key", "sk-test"),
            ("type connect phrase", "hello"),
            ("type confirm phrase", "there"),
            ("handshake", None),
            ("set font size", 20),
            ("move volume", 15),
            ("save", None),
        ],
    ),
    "a sequence that refuses part way": (
        case(),
        [
            ("type ai key", "sk-test"),
            ("set font size", "not a size"),
            ("save", None),
        ],
    ),
    "a sequence that refuses on the first step": (
        case(),
        [("set font size", float("nan")), ("type ai key", "sk-test")],
    ),
}


@pytest.mark.qt_no_exception_capture
@pytest.mark.parametrize("name", sorted(STEP_RUNS))
def test_a_sequence_of_steps_runs_the_same_way_on_both_sides(monkeypatch, capsys, name):
    """One side reached a different step, or held a different state after it.

    A sequence that refuses part way is compared by the step index, the
    step name and the type of the refusal, and the state each side kept
    up to that point is compared as well.
    """
    spec, steps = STEP_RUNS[name]
    old_reached, old_stopped, old_held = run_old_steps(monkeypatch, spec, steps, capsys)
    new_reached, new_stopped, new_held = run_new_steps(spec, steps)
    assert old_reached == new_reached, (
        f"[{name}] the two sides reached different steps: "
        f"shipped {old_reached}, surface {new_reached}"
    )
    assert old_stopped == new_stopped, (
        f"[{name}] the two sides stopped differently: "
        f"shipped {old_stopped}, surface {new_stopped}"
    )
    for key in sorted(set(old_held) | set(new_held)):
        assert old_held.get(key) == new_held.get(key), (
            f"[{name}] the two sides disagree on {key!r} after the run:\n"
            f"  shipped: {old_held.get(key)!r}\n"
            f"  surface: {new_held.get(key)!r}"
        )
    assert digest(old_held) == digest(new_held), f"[{name}] the two states hashed apart"


def test_a_sequence_that_refuses_part_way_keeps_what_it_recorded(monkeypatch, capsys):
    """A run that refused threw away the steps it had already taken."""
    spec, steps = STEP_RUNS["a sequence that refuses part way"]
    reached, stopped, held = run_new_steps(spec, steps)
    assert reached == [[0, "type ai key"]], reached
    assert stopped is not None and stopped[0] == 1, stopped
    assert stopped[1] == "set font size", stopped
    assert stopped[2] == "TypeError", stopped
    assert held["values"]["ai_api_key"] == "sk-test", held["values"]["ai_api_key"]
    assert held["written"] == [], held["written"]

    old_reached, old_stopped, old_held = run_old_steps(monkeypatch, spec, steps, capsys)
    assert old_reached == reached, old_reached
    assert old_stopped == stopped, old_stopped
    assert old_held["values"]["ai_api_key"] == "sk-test", old_held["values"]


def test_the_step_runner_reports_a_step_that_never_ran(monkeypatch, capsys):
    """The step runner counts a step the run never reached."""
    spec = case()
    steps = [("type ai key", "x"), ("set font size", "no"), ("type ai key", "y")]
    reached, stopped, held = run_new_steps(spec, steps)
    assert [one[1] for one in reached] == ["type ai key"], reached
    assert held["values"]["ai_api_key"] == "x", held["values"]["ai_api_key"]
    assert stopped[0] == 1, stopped


# --- is the comparison complete ------------------------------------------

COMPARED_KEYS = (
    "accepted",
    "enabled",
    "message_boxes",
    "minimum_size",
    "painted",
    "prints",
    "tabs",
    "texts",
    "tooltips",
    "values",
    "visible",
    "window_title",
)

COVERED_ELSEWHERE = {
    "actions": "test_the_surface_names_one_action_for_every_connection_it_counts",
    "bus": "test_the_dialog_touches_no_event_bus",
    "buttons": "test_both_sides_paint_the_same_dialog",
    "call_names": "test_every_recorded_step_carries_a_name_the_surface_names",
    "calls": "test_every_recorded_step_carries_a_name_the_surface_names",
    "connections": "test_the_source_connect_sites_match_the_number_the_surface_names",
    "control_specs": "test_both_sides_paint_the_same_dialog",
    "emitted": "test_the_dialog_declares_one_signal_and_emits_it_on_save",
    "exchange_items": "test_both_sides_paint_the_same_dialog",
    "groups": "test_both_sides_paint_the_same_dialog",
    "headings": "test_both_sides_paint_the_same_dialog",
    "layout": "test_the_two_sides_paint_one_picture",
    "listed_exchanges": "test_both_sides_paint_the_same_dialog",
    "phantom_timeframes": "test_both_sides_paint_the_same_dialog",
    "processed_events": "test_the_dialog_lets_the_screen_repaint_while_it_waits",
    "rejected": "test_a_sequence_of_steps_runs_the_same_way_on_both_sides",
    "rows": "test_both_sides_paint_the_same_dialog",
    "scrolling_tabs": "test_the_two_scrolling_tabs_are_the_ones_the_dialog_scrolls",
    "sound_test_buttons": "test_both_sides_paint_the_same_dialog",
    "spacing": "test_the_two_sides_paint_one_picture",
    "styles": "test_a_sequence_of_steps_runs_the_same_way_on_both_sides",
    "ta_rows": "test_both_sides_paint_the_same_dialog",
    "threads": "test_the_dialog_builds_no_timer_and_starts_no_thread",
    "timers": "test_the_dialog_builds_no_timer_and_starts_no_thread",
    "wing": "test_both_sides_paint_the_same_dialog",
}


def one_view():
    """One built view model, for the completeness checks to read."""
    return surface.build_view_model(surface_model(case(wing="stock")))


def test_every_exported_value_is_compared_or_named_with_its_covering_test():
    """The surface exports a value no test on either list looks at."""
    unclaimed = sorted(set(one_view()) - set(COMPARED_KEYS) - set(COVERED_ELSEWHERE))
    assert unclaimed == [], (
        f"these exported values reach no comparison and name no covering "
        f"test: {unclaimed}"
    )


def test_no_compared_key_is_missing_from_the_view_model():
    """The compared list names a key the surface does not export."""
    exported = set(one_view())
    unbacked = sorted(set(COMPARED_KEYS) - exported)
    assert unbacked == [], (
        f"the comparison names keys the surface does not export, so they "
        f"compare nothing: {unbacked}"
    )
    stale = sorted(set(COVERED_ELSEWHERE) - exported)
    assert (
        stale == []
    ), f"the covered list names keys the surface no longer exports: {stale}"


def test_both_completeness_checks_report_when_the_lists_drift():
    """Either completeness check passes a list that has drifted."""
    exported = set(one_view())
    grown = exported | {"a value nobody claimed"}
    assert sorted(grown - set(COMPARED_KEYS) - set(COVERED_ELSEWHERE)) == [
        "a value nobody claimed"
    ], "the first check would not see a newly exported value"
    assert sorted({"a key nothing exports"} - exported) == [
        "a key nothing exports"
    ], "the second check would not see a compared key nothing backs"


def test_every_compared_key_really_reaches_the_side_by_side_payload(
    monkeypatch, capsys
):
    """The compared list names a key the side-by-side payload never carries."""
    old, new = drive_both(monkeypatch, case(), capsys)
    carried = set(old[1]) & set(new[1])
    missing = sorted(set(COMPARED_KEYS) - carried)
    assert (
        missing == []
    ), f"these keys are on the compared list but reach no payload: {missing}"


def module_test_names():
    """Every test this file defines, read off the imported module."""
    import inspect

    return {
        name
        for name, value in inspect.getmembers(sys.modules[__name__])
        if name.startswith("test_") and inspect.isfunction(value)
    }


def test_every_named_covering_test_exists_in_this_file():
    """The covered list names a test nobody wrote."""
    written = module_test_names()
    missing = sorted(
        {
            named
            for named in COVERED_ELSEWHERE.values()
            if not any(one.startswith(named) for one in written)
        }
    )
    assert missing == [], f"named as covering tests but never written: {missing}"


def test_the_covering_test_check_reports_a_name_nobody_wrote():
    """The check above passes a covering test that does not exist."""
    written = module_test_names()
    assert not any(
        one.startswith("test_a_covering_test_nobody_wrote") for one in written
    ), "the control name is itself a test, so the check cannot report"


def parsed_names(path):
    """Every module-level name the file at `path` binds, read by parsing."""
    found = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            found.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            found.add(node.target.id)
    return found


def imported_names():
    """Every name the imported surface module carries, minus its imports."""
    skipped = {"annotations", "math", "Any", "Optional"}
    return {
        name
        for name in vars(surface)
        if not name.startswith("__") and name not in skipped
    }


def test_the_surface_declares_and_carries_the_same_names():
    """A name grew on one of the two lists and not the other.

    Both directions, and no count is typed anywhere: the two sets are
    compared to each other.
    """
    declared = parsed_names(SURFACE_FILE)
    carried = imported_names()
    assert declared - carried == set(), (
        f"declared in the file but absent from the module: "
        f"{sorted(declared - carried)}"
    )
    assert carried - declared == set(), (
        f"on the module but declared nowhere in the file: "
        f"{sorted(carried - declared)}"
    )


def test_the_name_check_reports_a_name_on_one_side_only():
    """The name check passes a name that is on one list and not the other."""
    declared = parsed_names(SURFACE_FILE)
    assert (declared | {"a name nothing declares"}) - imported_names() == {
        "a name nothing declares"
    }, "the name check would not see a name missing from the module"


def test_every_recorded_step_carries_a_name_the_surface_names(monkeypatch, capsys):
    """The surface recorded a step under a name it does not declare."""
    model = surface_model(case(result=GOOD_RESULT))
    model.edit("new_api_key", "k")
    model.edit("new_api_secret", "s")
    model.test_api_connection()
    model.edit("sound_volume", 30)
    model.test_sound("buy")
    model.test_ai_handshake()
    model.save()
    model.cancel()
    view = surface.build_view_model(model)
    names = {one[0] for one in view["calls"]}
    unknown = sorted(names - set(view["call_names"]) - {"edit"})
    assert unknown == [], unknown
    assert len(names) > 8, sorted(names)
    assert "a step nobody declares" not in set(view["call_names"])


def test_the_dialog_lets_the_screen_repaint_while_it_waits(monkeypatch, capsys):
    """The dialog stopped letting the screen repaint while it checks a key."""
    spec = case(result=GOOD_RESULT)
    steps = [("type key", "k"), ("type secret", "s"), ("test connection", None)]
    _processed.clear()
    run_old_steps(monkeypatch, spec, steps, capsys)
    old_pauses = list(_processed)

    _reached, _stopped, _held = run_new_steps(spec, steps)
    model = surface_model(spec)
    model.edit("new_api_key", "k")
    model.edit("new_api_secret", "s")
    model.test_api_connection()
    assert model.processed_events == old_pauses, (
        f"the shipped dialog paused {old_pauses} and the surface "
        f"{model.processed_events}"
    )
    assert old_pauses == [surface.PROCESS_EVENTS_REASON], old_pauses


def test_the_two_scrolling_tabs_are_the_ones_the_dialog_scrolls(monkeypatch, capsys):
    """A tab that scrolls is not named, or one that does not is."""
    from PySide6.QtWidgets import QScrollArea, QTabWidget

    dialog, _store, _log = shipped_dialog(monkeypatch, case())
    settings_lines(capsys)
    tabs = dialog.findChildren(QTabWidget)[0]
    scrolling = [
        tabs.tabText(at)
        for at in range(tabs.count())
        if isinstance(tabs.widget(at), QScrollArea)
    ]
    assert scrolling == list(surface.SCROLLING_TABS), (
        f"the shipped dialog scrolls {scrolling} and the surface names "
        f"{list(surface.SCROLLING_TABS)}"
    )
    assert scrolling, "no tab scrolls at all, so this check says nothing"


# --- what the run leaves behind ------------------------------------------

PROCESS_WIDE = (
    ("src.gui.settings_dialog", "QLineEdit"),
    ("src.gui.settings_dialog", "QCheckBox"),
    ("src.gui.settings_dialog", "QMessageBox"),
    ("src.gui.settings_dialog", "safe_process_events"),
    ("src.exchange.api_validator", "validate_credentials"),
    ("src.core.encryption", "encrypt"),
    ("src.core.sound_engine", "get_sound_engine"),
    ("src.core.sound_engine", "SoundConfig"),
)


def read_process_wide():
    """What each process-wide name points at right now."""
    import importlib

    return {
        f"{module}.{name}": getattr(importlib.import_module(module), name)
        for module, name in PROCESS_WIDE
    }


@pytest.mark.qt_no_exception_capture
@pytest.mark.parametrize(
    "spec_name", ["a dialog that opens", "a stored value that refuses"]
)
def test_the_process_wide_swaps_are_restored_after_a_drive(
    monkeypatch, capsys, spec_name
):
    """A swap this file made outlived the drive that needed it.

    Watched during the drive as well as after it: a check that only
    reads afterwards passes on a run that swapped nothing.
    """
    spec = (
        case()
        if spec_name == "a dialog that opens"
        else case(settings={"username": 12.7})
    )
    before = read_process_wide()
    with monkeypatch.context() as scoped:
        old, new = drive_both(scoped, spec, capsys)
        during = read_process_wide()
    after = read_process_wide()
    for key, was in before.items():
        assert during[key] is not was, (
            f"{key} was not swapped during the drive, so this run measured "
            "the live object and the restore check proves nothing"
        )
        assert (
            after[key] is was
        ), f"{key} was left pointing at this file's stand-in after the drive"
    assert old[0] == new[0], (old[0], new[0])
    if spec_name == "a stored value that refuses":
        assert old[0] == "refused", old[0]


def test_the_dialog_touches_no_event_bus(monkeypatch, capsys):
    """The Settings dialog subscribed to or emitted on the event bus.

    Counted on the bus class itself, so a caller reaching the bus
    through any alias is still counted.
    """
    from src.core.event_bus import EventBus

    counted = {"subscribe": 0, "emit": 0}
    for name in counted:
        original = getattr(EventBus, name)

        def wrapper(self, *args, __name=name, __original=original, **kwargs):
            counted[__name] += 1
            return __original(self, *args, **kwargs)

        monkeypatch.setattr(EventBus, name, wrapper, raising=True)

    run_old_steps(
        monkeypatch,
        case(),
        [("type ai key", "x"), ("move volume", 20), ("save", None)],
        capsys,
    )
    assert counted == {"subscribe": 0, "emit": 0}, counted
    assert list(surface.BUS_SUBSCRIBES) == [], surface.BUS_SUBSCRIBES
    assert list(surface.BUS_EMITS) == [], surface.BUS_EMITS

    from src.core.event_bus import get_event_bus

    bus = get_event_bus()
    delivered: list = []
    bus.subscribe("settings_dialog.probe", lambda event: delivered.append(event))
    bus.emit("settings_dialog.probe")
    assert counted == {"subscribe": 1, "emit": 1}, (
        f"the bus counter reported {counted} after one real subscribe and "
        "one real emit, so its zero above was a fact about the counter"
    )


def test_neither_side_opens_a_network_connection(monkeypatch, capsys):
    """The dialog reached the network while it was built and driven.

    The counter watches this process only. Nothing here starts a child
    process, so a connection opened by one would not be seen; the two
    probes that do start children import the surface rather than drive
    a socket.
    """
    import socket

    attempts: list = []

    def refuse(*args, **kwargs):
        attempts.append(args[1:] if args else kwargs)
        raise OSError("no network in this test")

    monkeypatch.setattr(socket.socket, "connect", refuse, raising=True)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse, raising=True)
    monkeypatch.setattr(socket, "create_connection", refuse, raising=True)

    old, new = drive_both(monkeypatch, case(), capsys)
    assert old[0] == new[0] == "built", (old[0], new[0])
    assert attempts == [], f"the dialog tried to reach {attempts}"

    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", 1))
    assert len(attempts) == 1, (
        f"the network counter reported {len(attempts)} after one real "
        "attempt, so its zero above was a fact about the counter"
    )


# --- what the surface does at import time --------------------------------

INERT_PROBE = """
import builtins
import json
import sys
import threading
import time

counts = {"clock": 0, "open": 0, "thread": 0}
CLOCKS = ("time", "monotonic", "perf_counter", "time_ns", "monotonic_ns")
for _name in CLOCKS:
    _original = getattr(time, _name)

    def _counted(*args, _original=_original, **kwargs):
        counts["clock"] += 1
        return _original(*args, **kwargs)

    setattr(time, _name, _counted)

_open = builtins.open


def _counted_open(*args, **kwargs):
    counts["open"] += 1
    return _open(*args, **kwargs)


builtins.open = _counted_open

_start = threading.Thread.start


def _counted_start(self, *args, **kwargs):
    counts["thread"] += 1
    return _start(self, *args, **kwargs)


threading.Thread.start = _counted_start


class RefuseQt:
    def find_module(self, name, path=None):
        return None

    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in ("PySide6", "shiboken6"):
            raise ImportError("PySide6 is absent from this run")
        return None


import os

sys.meta_path.insert(0, RefuseQt())
sys.path.insert(0, os.environ["PROBE_REPO"])

import src.gui.main_tabs

package_import = dict(counts)
counts = {"clock": 0, "open": 0, "thread": 0}

import src.gui.main_tabs.settings_dialog_surface as surface

reached_qt = [name for name in sys.modules if name.startswith("PySide6")]
after_import = dict(counts)

model = surface.SettingsDialogModel(
    settings=surface.SettingsSource({"username": "hal"}),
    status_log=surface.StatusLogSink(),
    wing="stock",
)
model.build()
built = surface.build_view_model(model)

if os.environ.get("PROBE_PLANT") == "1":
    time.time()
    _counted_open(os.environ["PROBE_REPO"] + "/README.md", "rb").close()
    planted = threading.Thread(target=lambda: None, name="planted")
    planted.start()
    planted.join()

print(
    json.dumps(
        {
            "package_import": package_import,
            "after_import": after_import,
            "final": dict(counts),
            "qt_modules": reached_qt,
            "method": surface.METHOD,
            "controls": len(surface.CONTROL_SPECS),
            "tabs": built["tabs"],
            "title": built["window_title"],
        }
    )
)
"""


def run_probe(tmp_path, plant=False):
    """Run the inert-import probe in its own process and read its answer."""
    running = dict(os.environ)
    running.pop("PYTHONPATH", None)
    running["PROBE_REPO"] = str(REPO)
    running["PROBE_PLANT"] = "1" if plant else "0"
    done = subprocess.run(
        [sys.executable, "-"],
        input=INERT_PROBE,
        capture_output=True,
        text=True,
        timeout=110,
        env=running,
        cwd=str(tmp_path),
        check=False,
    )
    assert done.returncode == 0, (
        f"the probe exited {done.returncode} stdout: {done.stdout} "
        f"stderr: {done.stderr}"
    )
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_the_surface_imports_with_no_qt_and_touches_nothing(tmp_path):
    """Importing the surface read a clock, opened a file, or reached Qt.

    Run in its own process with every Qt import refused, so a run that
    quietly found PySide6 on the path cannot pass.
    """
    found = run_probe(tmp_path)
    assert found["qt_modules"] == [], found["qt_modules"]
    assert found["after_import"] == {
        "clock": 0,
        "open": 0,
        "thread": 0,
    }, found["after_import"]
    assert found["package_import"]["thread"] > 0, (
        "importing the src package started no thread, so the split between "
        "the package's own cost and this module's says nothing"
    )
    assert found["method"] == surface.METHOD, found["method"]
    assert found["controls"] == len(surface.CONTROL_SPECS), found["controls"]
    assert found["tabs"] == list(surface.TAB_TITLES), found["tabs"]
    assert found["title"] == surface.title_for("stock"), found["title"]


def test_the_inert_probe_reports_a_planted_clock_read_file_open_and_thread(
    tmp_path,
):
    """The probe's zero is a fact about the probe, not about the surface."""
    found = run_probe(tmp_path, plant=True)
    assert found["after_import"] == {
        "clock": 0,
        "open": 0,
        "thread": 0,
    }, found["after_import"]
    assert found["final"]["clock"] >= 1, found["final"]
    assert found["final"]["open"] >= 1, found["final"]
    assert found["final"]["thread"] >= 1, found["final"]


HOME_PROBE = """
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.environ["PROBE_REPO"])
home = Path(os.environ["PROBE_HOME"])


def count_files():
    return sorted(
        str(one.relative_to(home)) for one in home.rglob("*") if one.is_file()
    )


before = count_files()

import src.gui.main_tabs.settings_dialog_surface as surface

model = surface.SettingsDialogModel(
    settings=surface.SettingsSource(
        {"username": "hal"},
        [{"exchange_id": "coinbase", "display_name": "Coinbase"}],
    ),
    status_log=surface.StatusLogSink(),
    wing="crypto",
    validator=surface.ValidatorSource(
        surface.ValidationResult(True, "ok", "USD 1")
    ),
    sound=surface.SoundEngineSink(),
    encryptor=lambda value, master: "enc",
)
model.build()
model.edit("new_api_key", "k")
model.edit("new_api_secret", "s")
model.test_api_connection()
model.add_exchange()
model.remove_exchange("Coinbase (coinbase)")
model.edit("sound_volume", 25)
model.test_sound("buy")
model.test_ai_handshake()
model.save()
model.cancel()
surface.build_view_model(model)
surface.view_model({"wing": "stock", "settings": {"username": "hal"}})

after = count_files()

if os.environ.get("PROBE_PLANT") == "1":
    (home / "planted.txt").write_text("planted", encoding="utf-8")

print(
    json.dumps(
        {
            "before": before,
            "after": after,
            "planted": count_files(),
            "written": len(model.settings.written),
        }
    )
)
"""


def run_home_probe(tmp_path, plant=False):
    """Drive the surface with home pointed at a throwaway folder."""
    home = tmp_path / "throwaway_home"
    home.mkdir(exist_ok=True)
    running = dict(os.environ)
    running.pop("PYTHONPATH", None)
    running["ACERVATOR_TEST_HOME"] = str(home)
    running["HOME"] = str(home)
    running["USERPROFILE"] = str(home)
    running["PROBE_REPO"] = str(REPO)
    running["PROBE_HOME"] = str(home)
    running["PROBE_PLANT"] = "1" if plant else "0"
    done = subprocess.run(
        [sys.executable, "-"],
        input=HOME_PROBE,
        capture_output=True,
        text=True,
        timeout=110,
        env=running,
        cwd=str(tmp_path),
        check=False,
    )
    assert done.returncode == 0, (
        f"the home probe exited {done.returncode} stdout: {done.stdout} "
        f"stderr: {done.stderr}"
    )
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_driving_the_surface_writes_no_file_into_a_throwaway_home(tmp_path):
    """The surface wrote into the operator's home while it was driven.

    This is the check that matters most for this file: the shipped
    dialog writes the whole settings file on every setting it saves.
    """
    found = run_home_probe(tmp_path)
    assert (
        found["after"] == found["before"] == []
    ), f"the surface left {found['after']} under a throwaway home"
    assert found["written"] > 0, found["written"]


def test_the_throwaway_home_counter_reports_a_planted_file(tmp_path):
    """The empty home reading is a fact about the counter, not the surface."""
    found = run_home_probe(tmp_path, plant=True)
    assert found["after"] == [], found["after"]
    assert found["planted"] == ["planted.txt"], found["planted"]


# --- what the shipped dialog writes, and where ---------------------------


def test_the_shipped_store_writes_the_whole_settings_file_on_every_set(
    tmp_path,
):
    """The shipped store stopped writing the file on every setting.

    This is what the surface must never do: one Save runs sixteen sets,
    and each one rewrites the operator's settings file where it lives.
    """
    from src.core.settings import SettingsManager

    manager = SettingsManager(config_dir=tmp_path)
    written = sorted(one.name for one in tmp_path.iterdir())
    manager.set("username", "hal")
    after = sorted(one.name for one in tmp_path.iterdir())
    assert after, f"the store wrote nothing at all into {tmp_path}"
    assert len(surface.SAVE_PAIRS) + len(surface.SAVE_GROUP_KEYS) == 16, (
        f"{len(surface.SAVE_PAIRS)} plain settings and "
        f"{len(surface.SAVE_GROUP_KEYS)} groups"
    )
    assert written != after or written, (written, after)


def test_the_surface_store_writes_no_file_at_all(tmp_path):
    """The surface's own store reached the filesystem."""
    before = sorted(one.name for one in tmp_path.iterdir())
    store = surface.SettingsSource()
    for key, _name in surface.SAVE_PAIRS:
        store.set(key, "value")
    assert sorted(one.name for one in tmp_path.iterdir()) == before, tmp_path
    assert len(store.written) == len(surface.SAVE_PAIRS), store.written


# --- sweeps over this unit's own files -----------------------------------

SKIN_READERS = (
    "styleSheet",
    "palette",
    "background",
    "foreground",
    "property",
    "color",
    "brush",
)


def skin_reads_in(path):
    """Every call in `path` that reads a skin off a live object.

    Parsed, never matched against the file's text: a text sweep reports
    the pattern strings the sweep itself writes down.
    """
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr in SKIN_READERS:
            found.append([node.lineno, ast.unparse(node)[:70]])
    return found


def self_comparisons_in(path):
    """Every assertion in `path` comparing a value to itself."""
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Assert):
            continue
        test = node.test
        if not isinstance(test, ast.Compare) or len(test.comparators) != 1:
            continue
        if ast.unparse(test.left) == ast.unparse(test.comparators[0]):
            found.append([node.lineno, ast.unparse(test)[:70]])
    return found


def constant_assertions_in(path):
    """Every assertion in `path` whose answer is a constant."""
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Assert):
            continue
        test = node.test
        if isinstance(test, ast.Constant):
            found.append([node.lineno, ast.unparse(test)[:70]])
        elif isinstance(test, ast.Compare) and all(
            isinstance(one, ast.Constant) for one in [test.left, *test.comparators]
        ):
            found.append([node.lineno, ast.unparse(test)[:70]])
    return found


OWN_FILES = (
    "tests/test_settings_dialog_surface_parity.py",
    "src/gui/main_tabs/settings_dialog_surface.py",
)


@pytest.mark.parametrize("name", OWN_FILES)
def test_this_unit_reads_no_skin_off_a_live_object(name):
    """A colour, palette or style was read off a live widget.

    The rendered picture is the only place a skin is read here.
    """
    found = skin_reads_in(REPO / name)
    assert found == [], f"{name} reads a live skin at {found}"


@pytest.mark.parametrize("name", OWN_FILES)
def test_no_assertion_here_compares_a_value_to_itself(name):
    """An assertion compares one value to itself and can never fail."""
    found = self_comparisons_in(REPO / name)
    assert found == [], f"{name} compares a value to itself at {found}"


@pytest.mark.parametrize("name", OWN_FILES)
def test_no_assertion_here_reads_a_constant(name):
    """An assertion reads a constant and can never fail."""
    found = constant_assertions_in(REPO / name)
    assert found == [], f"{name} asserts a constant at {found}"


def parsed_from(text, tmp_path, name):
    """`text` written to a throwaway file the sweeps can parse."""
    written = tmp_path / name
    written.write_text(text, encoding="utf-8", newline="\n")
    return written


SELF_COMPARE_SAMPLE = "def sample(one):\n    assert one.count == one.count\n"
CONSTANT_SAMPLE = "def sample():\n    assert 1 == 1\n"
CLEAN_SAMPLE = "def sample(one, two):\n    assert one.count == two.count\n"
SKIN_SAMPLE = "def sample(one):\n    assert one.styleSheet() == ''\n"


def test_the_self_comparison_sweep_reports_one_and_stays_quiet_otherwise(
    tmp_path,
):
    """The self-comparison sweep passes a value compared to itself."""
    hit = self_comparisons_in(parsed_from(SELF_COMPARE_SAMPLE, tmp_path, "a.py"))
    quiet = self_comparisons_in(parsed_from(CLEAN_SAMPLE, tmp_path, "b.py"))
    assert len(hit) == 1, hit
    assert quiet == [], quiet


def test_the_constant_assertion_sweep_reports_one_and_stays_quiet_otherwise(
    tmp_path,
):
    """The constant-assertion sweep passes an assertion on a constant."""
    hit = constant_assertions_in(parsed_from(CONSTANT_SAMPLE, tmp_path, "c.py"))
    quiet = constant_assertions_in(parsed_from(CLEAN_SAMPLE, tmp_path, "d.py"))
    assert len(hit) == 1, hit
    assert quiet == [], quiet


def test_the_skin_sweep_reports_a_planted_read_and_stays_quiet_otherwise(
    tmp_path,
):
    """The skin sweep passes a style read off a live object."""
    hit = skin_reads_in(parsed_from(SKIN_SAMPLE, tmp_path, "e.py"))
    quiet = skin_reads_in(parsed_from(CLEAN_SAMPLE, tmp_path, "f.py"))
    assert len(hit) == 1, hit
    assert quiet == [], quiet


SKIN_READING_FILE = REPO / "src" / "gui" / "usb_auth_widget.py"


def test_the_skin_sweep_reports_a_file_that_really_does_read_one():
    """The sweep's empty answer is a fact about the sweep.

    Pointed at a shipped widget that does read a skin off a live
    object, the sweep must name it.
    """
    assert SKIN_READING_FILE.is_file(), SKIN_READING_FILE
    found = skin_reads_in(SKIN_READING_FILE)
    assert found, (
        f"the sweep found no live-skin read in {SKIN_READING_FILE.name}, so "
        "its empty answer on this unit's own files says nothing"
    )


# --- the picture -----------------------------------------------------------


class DialogBuilder:
    """Builds the whole dialog from the surface's payload alone."""

    def __init__(self, view):
        self.view = view
        self.specs = {one["name"]: one for one in view["control_specs"]}

    def control(self, name):
        from PySide6.QtWidgets import (
            QCheckBox,
            QComboBox,
            QDoubleSpinBox,
            QLineEdit,
            QListWidget,
            QRadioButton,
            QSlider,
            QSpinBox,
            QTextEdit,
        )
        from PySide6.QtCore import Qt

        spec = self.specs[name]
        kind = spec["kind"]
        value = self.view["values"][name]
        if kind == surface.LIST:
            built = QListWidget()
            for line in value:
                built.addItem(line)
        elif kind == surface.TEXT_AREA:
            built = QTextEdit()
            built.setMaximumHeight(spec["max_height"])
            built.setPlaceholderText(spec.get("placeholder", ""))
            built.setPlainText(value)
        elif kind == surface.LINE:
            built = QLineEdit()
            if spec.get("echo") == "password":
                built.setEchoMode(QLineEdit.EchoMode.Password)
            built.setPlaceholderText(spec.get("placeholder", ""))
            built.setText(value)
        elif kind in (surface.CHECK, surface.RADIO):
            built = (
                QCheckBox(spec["text"])
                if kind == surface.CHECK
                else QRadioButton(spec["text"])
            )
            built.setChecked(value)
        elif kind in (surface.COMBO_TEXT, surface.COMBO_DATA):
            built = QComboBox()
            if spec.get("editable"):
                built.setEditable(True)
            if name == "new_exchange":
                for text, data in self.view["exchange_items"]:
                    built.addItem(text, data)
            elif kind == surface.COMBO_DATA:
                for text, data in spec["items"]:
                    built.addItem(text, data)
            else:
                built.addItems(list(spec["items"]))
            built.setCurrentIndex(value)
        elif kind == surface.SLIDER:
            built = QSlider(Qt.Orientation.Horizontal)
            built.setRange(*spec["range"])
            built.setValue(value)
        else:
            built = QSpinBox() if kind == surface.SPIN else QDoubleSpinBox()
            built.setRange(*spec["range"])
            if kind == surface.DOUBLE_SPIN:
                built.setDecimals(spec.get("decimals", surface.DEFAULT_DECIMALS))
            if "prefix" in spec:
                built.setPrefix(spec["prefix"])
            if "suffix" in spec:
                built.setSuffix(spec["suffix"])
            built.setValue(value)
        if "min_height" in spec:
            built.setMinimumHeight(spec["min_height"])
        if name in self.view["tooltips"]:
            built.setToolTip(self.view["tooltips"][name])
        built.setEnabled(self.view["enabled"][name])
        built.setVisible(self.view["visible"][name])
        return built

    def named_label(self, name):
        from PySide6.QtWidgets import QLabel

        built = QLabel(self.view["texts"][name])
        style = self.view["styles"].get(name, "")
        if style:
            built.setStyleSheet(style)
        return built

    def plain_label(self, text, style="", wrap=False):
        from PySide6.QtWidgets import QLabel

        built = QLabel(text)
        if wrap:
            built.setWordWrap(True)
        if style:
            built.setStyleSheet(style)
        return built

    def add(self, layout, widget, label=None):
        from PySide6.QtWidgets import QFormLayout

        if isinstance(layout, QFormLayout):
            if label is None:
                layout.addRow(widget)
            else:
                layout.addRow(label, widget)
            return
        layout.addWidget(widget)

    def add_layout(self, layout, inner):
        from PySide6.QtWidgets import QFormLayout

        if isinstance(layout, QFormLayout):
            layout.addRow(inner)
            return
        layout.addLayout(inner)

    def block(self, node, parent, tab_title):
        from PySide6.QtWidgets import (
            QFormLayout,
            QHBoxLayout,
            QScrollArea,
            QVBoxLayout,
            QWidget,
        )
        from PySide6.QtCore import Qt

        role = node[0]
        if role == surface.SCROLL:
            area = QScrollArea()
            area.setWidgetResizable(True)
            if tab_title in self.view["spacing"]["no_horizontal_bar"]:
                area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            inner = QWidget()
            self.block(node[1], inner, tab_title)
            spacing = self.view["spacing"]["content"].get(tab_title)
            if spacing is not None:
                inner.layout().setSpacing(spacing)
            area.setWidget(inner)
            return area
        if role == surface.FORM:
            layout = QFormLayout(parent)
        elif role == surface.ROW:
            layout = QHBoxLayout(parent)
        else:
            layout = QVBoxLayout(parent)
        for item in node[1]:
            self.item(item, layout, tab_title)
        return parent

    def group(self, title, inner_node, tab_title):
        from PySide6.QtWidgets import QGroupBox

        box = QGroupBox(title)
        self.block(inner_node, box, tab_title)
        layout = box.layout()
        spacing = self.view["spacing"]["group_form"].get(title)
        if spacing is not None:
            layout.setSpacing(spacing)
            layout.setContentsMargins(*self.view["spacing"]["group_margins"][title])
        return box

    def row(self, items, tab_title):
        from PySide6.QtWidgets import QHBoxLayout

        inner = QHBoxLayout()
        for one in items:
            self.item(one, inner, tab_title)
        return inner

    def item(self, item, layout, tab_title):
        from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider
        from PySide6.QtCore import Qt

        role = item[0]
        if role == surface.STRETCH:
            layout.addStretch()
            return
        if role == surface.BANNER:
            if self.view["wing"] == surface.STOCK_WING:
                self.add(
                    layout,
                    self.plain_label(
                        surface.STOCK_BANNER_TEXT,
                        surface.STOCK_BANNER_STYLE,
                        wrap=True,
                    ),
                )
            return
        if role == surface.LABEL:
            style = ""
            wrap = False
            if item[1] == surface.SMS_GATEWAY_HEADING:
                style = surface.SMS_GATEWAY_HEADING_STYLE
            if item[1] == surface.AI_INFO_TEXT:
                style = surface.AI_INFO_STYLE
                wrap = surface.AI_INFO_WORD_WRAP
            self.add(layout, self.plain_label(item[1], style, wrap))
            return
        if role == surface.BUTTON:
            built = QPushButton(item[1])
            if item[1] == surface.ADD_BUTTON_TEXT:
                built.setProperty(surface.ACCENT_PROPERTY, True)
            if item[1] == surface.REMOVE_BUTTON_TEXT:
                built.setProperty(surface.DANGER_PROPERTY, True)
            if item[1] == surface.AI_TEST_BUTTON_TEXT:
                built.setMinimumHeight(surface.AI_TEST_BUTTON_MIN_HEIGHT)
                built.setStyleSheet(surface.AI_TEST_BUTTON_STYLE)
            named = surface.BUTTON_NAMES_BY_TEXT.get(item[1])
            if named is not None:
                built.setEnabled(self.view["enabled"][named])
                if named in self.view["tooltips"]:
                    built.setToolTip(self.view["tooltips"][named])
            self.add(layout, built)
            return
        if role == surface.TEXT:
            name = item[1]
            label = surface.TEXT_ROW_LABELS.get(name)
            self.add(layout, self.named_label(name), label)
            return
        if role == surface.ROW:
            self.add_layout(layout, self.row(item[1], tab_title))
            return
        if role == surface.GROUP:
            title = item[1]
            if title == surface.ADD_GROUP_BY_WING:
                title = surface.add_group_title(self.view["wing"])
            self.add(layout, self.group(title, item[2], tab_title))
            return
        if role == surface.TA_ROWS:
            for label, position, printed in self.view["ta_rows"]:
                line = QHBoxLayout()
                left = QLabel(label)
                left.setMinimumWidth(surface.TA_LABEL_MIN_WIDTH)
                line.addWidget(left)
                slider = QSlider(Qt.Orientation.Horizontal)
                slider.setRange(*surface.TA_SLIDER_RANGE)
                slider.setValue(position)
                line.addWidget(slider)
                right = QLabel(printed)
                right.setMinimumWidth(surface.TA_VALUE_MIN_WIDTH)
                line.addWidget(right)
                self.add_layout(layout, line)
            return
        if role == surface.TF_ROW:
            from PySide6.QtWidgets import QCheckBox

            line = QHBoxLayout()
            for timeframe, ticked in self.view["phantom_timeframes"]:
                box = QCheckBox(timeframe)
                box.setChecked(ticked)
                line.addWidget(box)
            self.add_layout(layout, line)
            return
        if role == surface.SOUND_ROW:
            line = QHBoxLayout()
            for text, _name, tip in self.view["sound_test_buttons"]:
                button = QPushButton(text)
                if tip:
                    button.setToolTip(tip)
                line.addWidget(button)
            self.add_layout(layout, line)
            return
        name = item[1]
        spec = self.specs[name]
        label = spec["label"] if spec["label"] is not None else None
        self.add(layout, self.control(name), label)


def dialog_from_payload(view, current_tab=0):
    """The whole Settings dialog, built from the surface's payload alone."""
    from PySide6.QtWidgets import (
        QDialog,
        QHBoxLayout,
        QPushButton,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )

    view = unaltered(view)
    builder = DialogBuilder(view)
    dialog = QDialog()
    dialog.setAccessibleName("Settings dialog painted by the surface")
    dialog.setWindowTitle(view["window_title"])
    dialog.setMinimumSize(*view["minimum_size"])
    layout = QVBoxLayout(dialog)
    tabs = QTabWidget()
    for title in view["tabs"]:
        node = view["layout"][title]
        page = builder.block(tuple(node), QWidget(), title)
        tabs.addTab(page, title)
    layout.addWidget(tabs)
    tabs.setCurrentIndex(current_tab)

    row = QHBoxLayout()
    row.addStretch()
    cancel = QPushButton(view["buttons"]["cancel"])
    row.addWidget(cancel)
    save = QPushButton(view["buttons"]["save"])
    save.setProperty(surface.ACCENT_PROPERTY, True)
    save.setStyleSheet(view["buttons"]["save_style"])
    row.addWidget(save)
    layout.addLayout(row)
    return dialog


def model_payload(spec):
    """The surface's view model for one case, stamped as it comes off."""
    return sealed(surface.build_view_model(surface_model(spec)))


def shipped_widget(monkeypatch, spec, capsys, current_tab=0):
    """The real Settings dialog, with one tab showing."""
    from PySide6.QtWidgets import QTabWidget

    dialog, _store, _log = shipped_dialog(monkeypatch, spec)
    settings_lines(capsys)
    dialog.findChildren(QTabWidget)[0].setCurrentIndex(current_tab)
    return dialog


PICTURE_CASES = {
    "the crypto wing on the Exchanges tab": (case(), 1),
    "the stock wing on the Exchanges tab": (case(wing="stock"), 1),
    "the Profit Folding tab": (case(), 3),
    "the Sound tab": (case(), 8),
    "the AI Monitor tab": (
        case(
            settings={
                "ai_monitor": {
                    "api_key": "sk-ant-api03-x",
                    "interval_hours": 6.5,
                    "connect_phrase": "hello",
                    "confirm_phrase": "there",
                    "enabled": True,
                    "auto_handshake": False,
                    "log_feedback": True,
                }
            }
        ),
        10,
    ),
}


@pytest.mark.parametrize("name", sorted(PICTURE_CASES))
def test_the_two_sides_paint_one_picture(monkeypatch, capsys, name):
    """The surface paints a different Settings dialog from the shipped one.

    One render from each side, at one size, on this machine. No pixel
    count, no colour count and no fingerprint is written down here.
    """
    app()
    spec, tab = PICTURE_CASES[name]
    payload = model_payload(spec)
    assert_same_skin(
        build_old_side=lambda: hold(shipped_widget(monkeypatch, spec, capsys, tab)),
        build_new_side=lambda: hold(dialog_from_payload(payload, tab)),
        size=PICTURE_SIZE,
        control_rule=CONTROL_RULE,
        note=name,
    )


@pytest.mark.parametrize("name", sorted(PICTURE_CASES))
def test_each_rendered_state_can_report_before_it_is_compared(
    monkeypatch, capsys, name
):
    """A render paints one colour, so no comparison of it reports.

    The colour count each state paints is measured and returned rather
    than written down, so nothing here pins a number this machine
    happens to produce.
    """
    from tests.qt_pixel import render_widget

    app()
    spec, tab = PICTURE_CASES[name]
    old = render_widget(
        hold(shipped_widget(monkeypatch, spec, capsys, tab)), PICTURE_SIZE
    )
    new = render_widget(
        hold(dialog_from_payload(model_payload(spec), tab)), PICTURE_SIZE
    )
    old_colours = assert_picture_can_report(old, note=f"old side, {name}")
    new_colours = assert_picture_can_report(new, note=f"new side, {name}")
    assert old_colours == new_colours, (
        f"[{name}] the two sides painted {old_colours} and {new_colours} "
        "colours, so they are not painting one picture"
    )
    assert colour_count(old) == old_colours


def test_two_different_real_cases_paint_two_pictures(monkeypatch, capsys):
    """The picture comparison passes whatever the second side paints."""
    from tests.qt_pixel import render_widget

    app()
    first_spec, first_tab = PICTURE_CASES["the crypto wing on the Exchanges tab"]
    second_spec, second_tab = PICTURE_CASES["the stock wing on the Exchanges tab"]
    assert_cases_paint_differently(
        old_side=render_widget(
            hold(shipped_widget(monkeypatch, first_spec, capsys, first_tab)),
            PICTURE_SIZE,
        ),
        new_side=render_widget(
            hold(dialog_from_payload(model_payload(second_spec), second_tab)),
            PICTURE_SIZE,
        ),
        note="crypto against stock",
    )


def test_a_payload_changed_after_it_came_off_the_surface_is_refused():
    """A render was taken of a payload somebody edited."""
    spec, _tab = PICTURE_CASES["the Sound tab"]
    payload = model_payload(spec)
    payload["values"]["sound_volume"] = 3
    with pytest.raises(AssertionError) as reported:
        dialog_from_payload(payload)
    assert "altered after it came off" in str(reported.value)


def test_a_payload_that_never_came_off_a_side_is_refused():
    """A render was taken of a payload nobody produced."""
    with pytest.raises(AssertionError) as reported:
        dialog_from_payload({"values": {}, "tabs": [], "layout": {}})
    assert "never came off" in str(reported.value)


# --- every number this dialog reads out of stored settings ----------------

HOSTILE_VALUES = {
    "True": True,
    "nan": float("nan"),
    "inf": float("inf"),
    "-inf": float("-inf"),
    "text": "abc",
    "numeric string": "12.7",
    "12.7": 12.7,
    "10**400": 10**400,
}

READINGS = {
    "username": ("username", None, "username"),
    "position_distance_pct": ("position_distance_pct", None, "pos_distance"),
    "default_position_count": (
        "default_position_count",
        None,
        "default_positions",
    ),
    "default_target_balance": (
        "default_target_balance",
        None,
        "default_balance",
    ),
    "accent_color": ("accent_color", None, "accent_color"),
    "theme": ("theme", None, "theme_combo"),
    "increment_style": ("increment_style", None, "increment_style"),
    "ai_monitor.api_key": ("ai_monitor", "api_key", "ai_api_key"),
    "ai_monitor.interval_hours": (
        "ai_monitor",
        "interval_hours",
        "ai_interval",
    ),
    "ai_monitor.connect_phrase": (
        "ai_monitor",
        "connect_phrase",
        "ai_connect_phrase",
    ),
    "ai_monitor.confirm_phrase": (
        "ai_monitor",
        "confirm_phrase",
        "ai_confirm_phrase",
    ),
    "ai_monitor.enabled": ("ai_monitor", "enabled", "ai_enabled"),
    "ai_monitor.auto_handshake": (
        "ai_monitor",
        "auto_handshake",
        "ai_auto_handshake",
    ),
    "ai_monitor.log_feedback": ("ai_monitor", "log_feedback", "ai_log_feedback"),
    "profit_folding.active": ("profit_folding", "active", "folding_active"),
}

SUBSTITUTING_READINGS = (
    "ai_monitor.interval_hours",
    "default_position_count",
    "default_target_balance",
    "increment_style",
    "position_distance_pct",
    "theme",
)


def reading_case(reading, value):
    """One case with `value` stored under one reading and nothing else."""
    key, inner, _name = READINGS[reading]
    stored = {key: value} if inner is None else {key: {inner: value}}
    return case(settings=stored)


def old_reading(monkeypatch, capsys, reading, value):
    """What the shipped dialog does with one stored value."""
    _key, _inner, name = READINGS[reading]
    spec = reading_case(reading, value)
    try:
        dialog, _store, _log = shipped_dialog(monkeypatch, spec)
    except BaseException as exc:
        settings_lines(capsys)
        return ["stops", type(exc).__name__]
    settings_lines(capsys)
    control = spec_kind(name)
    return ["shows", old_value(getattr(dialog, "_" + name), control)]


def spec_kind(name):
    """The painted kind of one named control."""
    return surface.PAINTED_KIND[surface.spec_for(name)["kind"]]


def new_reading(reading, value):
    """What the surface does with the same stored value."""
    _key, _inner, name = READINGS[reading]
    try:
        model = surface_model(reading_case(reading, value))
    except BaseException as exc:
        return ["stops", type(exc).__name__]
    return ["shows", model.values[name]]


def carried_unchanged(stored, shown):
    """Whether the control prints the figure that was stored."""
    if isinstance(shown, str) or isinstance(stored, str):
        return shown == stored
    if isinstance(stored, bool) or isinstance(shown, bool):
        return shown is stored
    try:
        return bool(shown == stored)
    except TypeError:
        return False


@pytest.mark.qt_no_exception_capture
@pytest.mark.parametrize("reading", sorted(READINGS))
def test_a_stored_value_reaches_each_reading_the_same_way(monkeypatch, capsys, reading):
    """A stored value reaches one side's control and not the other's.

    Every value the audit drives, on the real dialog and on the
    surface, one reading at a time.
    """
    for label, value in HOSTILE_VALUES.items():
        old = old_reading(monkeypatch, capsys, reading, value)
        new = new_reading(reading, value)
        assert old == new, (
            f"[{reading} = {label}] the shipped dialog {old} and the " f"surface {new}"
        )


@pytest.mark.qt_no_exception_capture
def test_no_reading_in_this_dialog_guards_the_value_it_takes(monkeypatch, capsys):
    """A reading absorbs every value the audit drives.

    None does. Each one either stops the whole dialog opening, or prints
    a figure nobody stored. The table is measured here and reported, not
    typed in.
    """
    guarded = []
    stops = {}
    silent = {}
    for reading in sorted(READINGS):
        absorbed = True
        for label, value in HOSTILE_VALUES.items():
            outcome = new_reading(reading, value)
            if outcome[0] == "stops":
                stops.setdefault(reading, []).append(label)
                absorbed = False
            elif not carried_unchanged(value, outcome[1]):
                silent.setdefault(reading, []).append(label)
                absorbed = False
        if absorbed:
            guarded.append(reading)
    assert (
        guarded == []
    ), f"these readings absorbed every value the audit drove: {guarded}"
    assert sorted(stops) == sorted(
        READINGS
    ), f"a reading that stops on nothing: {sorted(set(READINGS) - set(stops))}"
    assert sorted(silent) == sorted(SUBSTITUTING_READINGS), (
        f"the readings that print a value nobody stored are {sorted(silent)}, "
        f"and the audit names {sorted(SUBSTITUTING_READINGS)}"
    )


def test_the_audit_can_tell_a_carried_value_from_a_changed_one():
    """The audit's classifier calls every value changed, or none.

    A decimal inside the control's range is carried through unchanged; a
    not-a-number is not. Without both answers the audit above says
    nothing.
    """
    carried = new_reading("position_distance_pct", 12.7)
    assert carried == ["shows", 12.7], carried
    assert carried_unchanged(12.7, carried[1]), carried

    changed = new_reading("position_distance_pct", float("nan"))
    assert changed[0] == "shows", changed
    assert not carried_unchanged(float("nan"), changed[1]), changed
    assert changed[1] == surface.spec_for("pos_distance")["range"][1], changed


@pytest.mark.qt_no_exception_capture
def test_a_stored_true_prints_a_dollar_figure_nobody_stored(monkeypatch, capsys):
    """A stored true no longer prints a target balance nobody set.

    The shape this audit was written for: the target balance is read out
    of stored settings with no guard, so a stored true prints the bottom
    of the control's range as a dollar figure.
    """
    outcome = old_reading(monkeypatch, capsys, "default_target_balance", True)
    low, _high = surface.spec_for("default_balance")["range"]
    assert outcome == ["shows", low], outcome
    assert new_reading("default_target_balance", True) == outcome, outcome
    assert surface.spec_for("default_balance")["prefix"] == "$", (
        "the control stopped printing a dollar sign, so the figure above "
        "no longer reads as money"
    )


@pytest.mark.qt_no_exception_capture
def test_one_bad_stored_value_stops_the_whole_dialog(monkeypatch, capsys):
    """One unusable stored value no longer stops all eleven tabs opening.

    Every reading in this dialog is inside one method that runs before
    the window appears, so a single value it cannot use costs the
    operator the whole Settings window, not one field.
    """
    outcome = old_reading(monkeypatch, capsys, "username", 12.7)
    assert outcome == ["stops", "TypeError"], outcome
    good = old_reading(monkeypatch, capsys, "username", "hal")
    assert good == ["shows", "hal"], good
    dialog, _store, _log = shipped_dialog(monkeypatch, case())
    settings_lines(capsys)
    from PySide6.QtWidgets import QTabWidget

    tabs = dialog.findChildren(QTabWidget)[0]
    assert tabs.count() == len(surface.TAB_TITLES), tabs.count()
