"""The Qt Console tab and the Qt-free surface, driven side by side.

A failure means the view model describes a different control, a
different colour, a different size, a different timer, a different signal
connection or a different pane behaviour than ``ConsoleTabMixin`` builds
on the same input.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.gui.main_tabs import console_tab_surface as surface

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[1]
TAB_SOURCE = REPO_ROOT / "src" / "gui" / "main_tabs" / "console_tab.py"

TOUCHED = ("", "acervator")

INSERT = "insert"
CLEAR = "clear"


@pytest.fixture(scope="module")
def qapp():
    """The application object the widget comparisons render against."""
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    running = QApplication.instance()
    return running if running is not None else QApplication(sys.argv)


@pytest.fixture
def booted(qapp):
    """The Console tab built by the Qt mixin, with its tab widget.

    Logger handlers and levels for every node the build touches are
    restored afterwards, so the module leaves nothing behind for the rest
    of the suite.
    """
    from PySide6.QtWidgets import QTabWidget, QWidget

    from src.gui.main_tabs.console_tab import ConsoleTabMixin

    saved = {
        name: (list(logging.getLogger(name).handlers), logging.getLogger(name).level)
        for name in TOUCHED
    }
    for name in TOUCHED:
        logging.getLogger(name).handlers.clear()

    class _Host(QWidget, ConsoleTabMixin):
        def __init__(self, tabs) -> None:
            QWidget.__init__(self)
            self.setAccessibleName("Console tab parity host")
            self._main_tabs = tabs

        def _drain_signals(self) -> None:
            return None

        def _emit_console_health(self) -> None:
            return None

        def _refresh_console_pause_indicator(self) -> None:
            return None

        def _toggle_console_pause(self) -> None:
            return None

    tabs = QTabWidget()
    host = _Host(tabs)
    host._build_console_tab()
    try:
        yield host, tabs
    finally:
        host._signal_timer.stop()
        host._console_health_timer.stop()
        host._console_pause_refresh.stop()
        for handler in list(logging.getLogger("acervator").handlers):
            handler.close()
        host.deleteLater()
        tabs.deleteLater()
        qapp.processEvents()
        for name, (handlers, level) in saved.items():
            node = logging.getLogger(name)
            node.handlers[:] = handlers
            node.setLevel(level)


def margins(layout) -> list:
    box = layout.contentsMargins()
    return [box.left(), box.top(), box.right(), box.bottom()]


def child_stretch(layout) -> list:
    return [layout.stretch(index) for index in range(layout.count())]


def qt_trace(host, tabs) -> dict:
    """Every value the built Qt tab can be asked for, as plain data."""
    container = tabs.widget(0)
    outer = container.layout()
    bar = outer.itemAt(0).widget()
    bar_layout = bar.layout()
    order = []
    for index in range(bar_layout.count()):
        widget = bar_layout.itemAt(index).widget()
        order.append("stretch" if widget is None else type(widget).__name__)
    pause = bar_layout.itemAt(0).widget()
    indicator = bar_layout.itemAt(1).widget()
    clear = bar_layout.itemAt(3).widget()
    split = outer.itemAt(1).widget()
    signal_box = split.widget(1)
    box_layout = signal_box.layout()
    header = box_layout.itemAt(0).widget()
    pane = host._console
    view = host._signal_view
    formatter = host._console_log_handler.formatter
    return {
        "tab_title": tabs.tabText(0),
        "container": {
            "margins_px": margins(outer),
            "spacing_px": outer.spacing(),
            "child_stretch": child_stretch(outer),
        },
        "control_bar": {
            "margins_px": margins(bar_layout),
            "spacing_px": bar_layout.spacing(),
            "child_stretch": child_stretch(bar_layout),
            "style_sheet": bar.styleSheet(),
        },
        "control_bar_order": order,
        "pause_button": {
            "text": pause.text(),
            "checkable": pause.isCheckable(),
            "checked": pause.isChecked(),
            "style_sheet": pause.styleSheet(),
        },
        "pause_indicator": {
            "text": indicator.text(),
            "style_sheet": indicator.styleSheet(),
        },
        "clear_button": {
            "text": clear.text(),
            "checkable": clear.isCheckable(),
            "style_sheet": clear.styleSheet(),
        },
        "signal_box": {
            "margins_px": margins(box_layout),
            "spacing_px": box_layout.spacing(),
            "child_stretch": child_stretch(box_layout),
        },
        "signal_header": {"text": header.text(), "style_sheet": header.styleSheet()},
        "splitter": {
            "orientation": split.orientation().name.lower(),
            "children": ["log_pane", "signal_box"],
            "stretch": [
                split.widget(0).sizePolicy().verticalStretch(),
                split.widget(1).sizePolicy().verticalStretch(),
            ],
            "holds_log_pane": split.widget(0) is pane,
            "holds_signal_view": box_layout.itemAt(1).widget() is view,
        },
        "log_pane": {
            "read_only": pane.isReadOnly(),
            "font_family": pane.font().family(),
            "font_point_size": pane.font().pointSize(),
            "wrap": pane.lineWrapMode().name != "NoWrap",
            "center_on_scroll": pane.centerOnScroll(),
            "max_blocks": pane.maximumBlockCount(),
            "style_sheet": pane.styleSheet(),
        },
        "signal_pane": {
            "read_only": view.isReadOnly(),
            "max_blocks": view.maximumBlockCount(),
            "style_sheet": view.styleSheet(),
        },
        "timers": {
            "drain": {
                "interval_ms": host._signal_timer.interval(),
                "running": host._signal_timer.isActive(),
            },
            "health": {
                "interval_ms": host._console_health_timer.interval(),
                "running": host._console_health_timer.isActive(),
            },
            "pause_refresh": {
                "interval_ms": host._console_pause_refresh.interval(),
                "running": host._console_pause_refresh.isActive(),
            },
        },
        "log_handler": {
            "format": formatter._fmt,
            "datefmt": formatter.datefmt,
            "loggers": [
                name
                for name in TOUCHED
                if host._console_log_handler in logging.getLogger(name).handlers
            ],
            "handler_level": host._console_log_handler.level,
        },
        "ledger": {
            "seq": host._signal_seq,
            "drain_ticks": host._signal_drain_ticks,
            "read": host._signal_read,
            "rendered": host._signal_rendered,
            "slice_dropped": host._signal_slice_dropped,
            "markers": host._signal_markers,
            "health_ticks_seen": host._signal_health_ticks_seen,
        },
    }


def surface_trace() -> dict:
    """The same values, read from the Qt-free view model."""
    model = surface.build_view_model(
        surface.ConsolePane(),
        surface.ConsolePane(surface.SIGNAL_MAX_BLOCKS),
        surface.SignalLedger(),
    )
    log_pane = model["log_pane"]
    signal_pane = model["signal_pane"]
    return {
        "tab_title": model["tab_title"],
        "container": dict(model["container"]),
        "control_bar": {
            "margins_px": model["control_bar"]["margins_px"],
            "spacing_px": model["control_bar"]["spacing_px"],
            "child_stretch": model["control_bar"]["child_stretch"],
            "style_sheet": model["control_bar"]["style_sheet"],
        },
        "control_bar_order": [
            "stretch" if name == "stretch" else WIDGET_CLASS[name]
            for name in model["control_bar_order"]
        ],
        "pause_button": {
            "text": model["pause_button"]["text"],
            "checkable": model["pause_button"]["checkable"],
            "checked": model["pause_button"]["checked"],
            "style_sheet": model["pause_button"]["style_sheet"],
        },
        "pause_indicator": {
            "text": model["pause_indicator"]["text"],
            "style_sheet": model["pause_indicator"]["style_sheet"],
        },
        "clear_button": {
            "text": model["clear_button"]["text"],
            "checkable": model["clear_button"]["checkable"],
            "style_sheet": model["clear_button"]["style_sheet"],
        },
        "signal_box": dict(model["signal_box"]),
        "signal_header": {
            "text": model["signal_header"]["text"],
            "style_sheet": model["signal_header"]["style_sheet"],
        },
        "splitter": {
            "orientation": model["splitter"]["orientation"],
            "children": model["splitter"]["children"],
            "stretch": model["splitter"]["stretch"],
            "holds_log_pane": True,
            "holds_signal_view": True,
        },
        "log_pane": {
            "read_only": log_pane["read_only"],
            "font_family": log_pane["font_family"],
            "font_point_size": log_pane["font_point_size"],
            "wrap": log_pane["wrap"],
            "center_on_scroll": log_pane["center_on_scroll"],
            "max_blocks": log_pane["max_blocks"],
            "style_sheet": log_pane["style_sheet"],
        },
        "signal_pane": {
            "read_only": signal_pane["read_only"],
            "max_blocks": signal_pane["max_blocks"],
            "style_sheet": signal_pane["style_sheet"],
        },
        "timers": model["timers"],
        "log_handler": model["log_handler"],
        "ledger": model["ledger"],
    }


WIDGET_CLASS = {
    "pause_button": "QPushButton",
    "pause_indicator": "QLabel",
    "clear_button": "QPushButton",
}


def digest(trace) -> str:
    return hashlib.sha256(
        json.dumps(trace, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def test_the_built_tab_and_the_surface_describe_the_same_tab(booted):
    """A control, colour, size, timer or counter differs between them."""
    host, tabs = booted
    old = qt_trace(host, tabs)
    new = surface_trace()
    assert new == old
    assert digest(new) == digest(old)


def test_the_trace_carries_every_part_of_the_tab(booted):
    """The comparison passed by comparing an empty or partial trace."""
    host, tabs = booted
    old = qt_trace(host, tabs)
    assert set(old) == set(surface_trace())
    assert len(old) == 15
    assert old["control_bar_order"] == [
        "QPushButton",
        "QLabel",
        "stretch",
        "QPushButton",
    ]
    assert old["log_handler"]["loggers"] == ["", "acervator"]
    assert old["log_pane"]["max_blocks"] == 2000
    assert sorted(old["ledger"]) == sorted(surface.LEDGER_FIELDS)


def dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def connect_sites() -> list:
    """Every ``.connect(`` site in the Qt tab, as signal and target."""
    tree = ast.parse(TAB_SOURCE.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "connect"
        ):
            found.append((dotted(node.func.value), dotted(node.args[0])))
    return sorted(found)


QT_SIGNAL_NAMES = {
    "self._console_pause_btn.clicked": "pause_button.clicked",
    "clear_btn.clicked": "clear_button.clicked",
    "self._signal_timer.timeout": "drain.timeout",
    "self._console_health_timer.timeout": "health.timeout",
    "self._console_pause_refresh.timeout": "pause_refresh.timeout",
}

QT_TARGET_NAMES = {
    "self._toggle_console_pause": "toggle_console_pause",
    "self._console.clear": "clear_log_pane",
    "self._drain_signals": "drain_signals",
    "self._emit_console_health": "emit_console_health",
    "self._refresh_console_pause_indicator": "refresh_console_pause_indicator",
}


def test_the_connect_sets_match():
    """The Qt tab connects a signal the surface names no action for."""
    sites = connect_sites()
    assert len(sites) == 5
    translated = {
        QT_SIGNAL_NAMES[signal]: QT_TARGET_NAMES[target] for signal, target in sites
    }
    assert translated == surface.ACTIONS


def test_the_connect_reader_finds_the_real_sites():
    """The connect reader returns an empty set whatever the source holds."""
    sites = connect_sites()
    assert ("self._signal_timer.timeout", "self._drain_signals") in sites
    assert TAB_SOURCE.read_text(encoding="utf-8").count(".connect(") == len(sites)


def insert_into(pane, text) -> None:
    cursor = pane.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    cursor.insertText(text)


def run_old_pane(script, max_blocks):
    """Drive a real ``QPlainTextEdit`` through the script and trace it."""
    from PySide6.QtWidgets import QPlainTextEdit

    pane = QPlainTextEdit()
    pane.setMaximumBlockCount(max_blocks)
    trace = []
    for step in script:
        if step[0] == CLEAR:
            pane.clear()
        else:
            insert_into(pane, step[1])
        trace.append(
            {
                "text": pane.toPlainText(),
                "block_count": pane.blockCount(),
                "is_empty": pane.document().isEmpty(),
            }
        )
    return trace


def run_new_pane(script, max_blocks):
    """Drive ``ConsolePane`` through the same script and trace it."""
    pane = surface.ConsolePane(max_blocks)
    trace = []
    for step in script:
        if step[0] == CLEAR:
            pane.clear()
        else:
            pane.insert(step[1])
        trace.append(
            {
                "text": pane.text(),
                "block_count": pane.block_count(),
                "is_empty": pane.is_empty(),
            }
        )
    return trace


def appended(lines):
    """The insert the log handler makes for each line, in order."""
    script = []
    for index, line in enumerate(lines):
        script.append((INSERT, line if index == 0 else "\n" + line))
    return script


APPEND_SCRIPT = appended(["first", "second", "third"])

OVERFLOW_SCRIPT = appended([f"line{n}" for n in range(1, 9)])

CLEAR_SCRIPT = [
    (INSERT, "before"),
    (INSERT, "\nsecond"),
    (CLEAR,),
    (INSERT, "after"),
    (CLEAR,),
    (CLEAR,),
]

BLANK_SCRIPT = [
    (INSERT, ""),
    (INSERT, "x"),
    (INSERT, ""),
    (INSERT, "\n"),
    (INSERT, "\n"),
]

NEWLINE_INTO_EMPTY_SCRIPT = [(INSERT, "\n"), (INSERT, "tail")]

PARTIAL_SCRIPT = [(INSERT, "abc"), (INSERT, "def"), (INSERT, "\nghi"), (INSERT, "jkl")]

MULTILINE_SCRIPT = [(INSERT, "a\nb\nc\nd\ne"), (INSERT, "\nf")]

TRAILING_NEWLINE_SCRIPT = [(INSERT, "a\nb\nc\nd\n")]

CAP_ONE_SCRIPT = appended(["a", "b", "c"])

REAL_CAP_SCRIPT = appended([f"r{n}" for n in range(2005)])

PANE_SCRIPTS = {
    "append": (APPEND_SCRIPT, surface.PANE_MAX_BLOCKS),
    "overflow": (OVERFLOW_SCRIPT, 5),
    "clear": (CLEAR_SCRIPT, surface.PANE_MAX_BLOCKS),
    "blank": (BLANK_SCRIPT, surface.PANE_MAX_BLOCKS),
    "newline_into_empty": (NEWLINE_INTO_EMPTY_SCRIPT, surface.PANE_MAX_BLOCKS),
    "partial": (PARTIAL_SCRIPT, surface.PANE_MAX_BLOCKS),
    "multiline": (MULTILINE_SCRIPT, 3),
    "trailing_newline": (TRAILING_NEWLINE_SCRIPT, 3),
    "cap_one": (CAP_ONE_SCRIPT, 1),
    "cap_zero": (OVERFLOW_SCRIPT, 0),
    "cap_negative": (OVERFLOW_SCRIPT, -1),
    "real_cap": (REAL_CAP_SCRIPT, surface.PANE_MAX_BLOCKS),
}


@pytest.mark.parametrize("name", sorted(PANE_SCRIPTS))
def test_the_pane_buffers_hold_the_same_text(qapp, name):
    """A step fills the Qt-free pane differently from the Qt pane."""
    script, max_blocks = PANE_SCRIPTS[name]
    old = run_old_pane(script, max_blocks)
    new = run_new_pane(script, max_blocks)
    assert new == old
    assert digest(new) == digest(old)


@pytest.mark.parametrize("name", sorted(PANE_SCRIPTS))
def test_the_pane_trace_measured_something(qapp, name):
    """The pane comparison passed on an empty trace."""
    script, max_blocks = PANE_SCRIPTS[name]
    old = run_old_pane(script, max_blocks)
    assert len(old) == len(script)
    assert any(step["text"] for step in old)


def test_the_cap_scripts_reach_the_cap(qapp):
    """A cap script never overflowed, so no eviction was compared."""
    overflow = run_old_pane(OVERFLOW_SCRIPT, 5)
    assert overflow[-1]["text"].splitlines() == [f"line{n}" for n in range(4, 9)]
    real = run_old_pane(REAL_CAP_SCRIPT, surface.PANE_MAX_BLOCKS)
    assert real[-1]["block_count"] == surface.PANE_MAX_BLOCKS
    assert real[-1]["text"].splitlines()[0] == "r5"
    unbounded = run_old_pane(OVERFLOW_SCRIPT, 0)
    assert unbounded[-1]["block_count"] == 8


RECORDS = [
    {"name": "acervator.gui", "level": "INFO", "message": "plain line", "created": 0.0},
    {
        "name": "acervator.exchange",
        "level": "ERROR",
        "message": "INDICATOR PANEL rsi 55",
        "created": 1000.5,
    },
    {"name": "", "level": "CRITICAL", "message": "no logger name", "created": 12345.0},
    {"name": "ccxt", "level": "TRACE", "message": "", "created": 99.0},
    {"name": "urllib3", "level": "", "message": None, "created": 7.0},
    {"name": "asyncio", "level": "DEBUG", "message": "percent %s left alone"},
]


def test_the_formatter_renders_the_same_line(booted):
    """The surface renders a console line the Qt formatter would not."""
    host, _tabs = booted
    formatter = host._console_log_handler.formatter
    old = []
    new = []
    for fields in RECORDS:
        message = fields.get("message")
        record = logging.LogRecord(
            name=str(fields.get("name") or ""),
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="" if message is None else str(message),
            args=(),
            exc_info=None,
        )
        record.levelname = str(fields.get("level") or "INFO")
        if fields.get("created") is not None:
            record.created = float(fields["created"])
        old.append(formatter.format(record))
        new.append(surface.format_record(fields))
    assert new == old
    assert digest(new) == digest(old)
    assert old[0].endswith("[INFO] acervator.gui: plain line")
    assert old[4].endswith("[INFO] urllib3: ")


def test_a_record_that_cannot_be_read_is_skipped():
    """An unreadable record raised instead of being skipped."""

    class _Raising:
        def get(self, _key, _default=None):
            raise ValueError("unreadable record")

    model = surface.build_view_model(
        surface.ConsolePane(),
        surface.ConsolePane(),
        surface.SignalLedger(),
        [_Raising()],
    )
    assert model["log_pane"]["text"] == ""
    assert model["log_pane"]["is_empty"] is True


def test_the_clear_button_empties_the_log_pane_only():
    """Clear left the log pane filled, or emptied the signals pane too."""
    log_pane = surface.ConsolePane()
    signal_pane = surface.ConsolePane()
    ledger = surface.SignalLedger()
    surface.build_view_model(
        log_pane, signal_pane, ledger, RECORDS[:2], ["sig one", "sig two"]
    )
    assert log_pane.block_count() == 2
    model = surface.build_view_model(log_pane, signal_pane, ledger, clear_log=True)
    assert model["log_pane"]["text"] == ""
    assert model["signal_pane"]["text"] == "sig one\nsig two"


RENDER_SIZE = (760, 540)

BUTTON_GROUND_INSET = 3
HEADER_RIGHT_INSET = 10
BAR_BOTTOM_INSET = 3


def tab_parts(host, container) -> dict:
    """Every painted part of the tab, keyed by its view-model name."""
    outer = container.layout()
    bar = outer.itemAt(0).widget()
    split = outer.itemAt(1).widget()
    box = split.widget(1).layout()
    return {
        "control_bar": bar,
        "log_pane": host._console,
        "signal_box": split.widget(1),
        "signal_header": box.itemAt(0).widget(),
        "signal_pane": host._signal_view,
        "pause_button": host._console_pause_btn,
        "pause_indicator": host._console_pause_indicator,
        "clear_button": bar.layout().itemAt(3).widget(),
    }


@pytest.fixture
def painted(booted):
    """The Console tab rendered once, with the widgets it was drawn from.

    The container is taken out of the tab widget first. A widget inside a
    layout is resized back by its parent, so a render of one asks for a
    size it never gets.
    """
    from PySide6.QtWidgets import QApplication

    from qt_pixel import render_widget

    host, tabs = booted
    container = tabs.widget(0)
    tabs.removeTab(0)
    container.setParent(None)
    try:
        yield host, container, render_widget(container, size=RENDER_SIZE)
    finally:
        for name in TOUCHED:
            logging.getLogger(name).removeHandler(host._console_log_handler)
        container.deleteLater()
        QApplication.processEvents()


def colour_at(image, container, widget, point) -> str:
    """The painted colour at a point inside `widget`."""
    from qt_pixel import pixel_at

    return pixel_at(image, widget.mapTo(container, point))


def ground_point(name, widget):
    """A point inside `widget` that carries its ground, not a glyph."""
    from PySide6.QtCore import QPoint

    rect = widget.rect()
    if name in ("pause_button", "clear_button"):
        return QPoint(BUTTON_GROUND_INSET, BUTTON_GROUND_INSET)
    if name == "signal_header":
        return QPoint(rect.width() - HEADER_RIGHT_INSET, rect.height() // 2)
    if name == "control_bar":
        return QPoint(rect.width() // 2, rect.height() - BAR_BOTTOM_INSET)
    return rect.center()


PAINTED_GROUNDS = [
    ("control_bar", surface.CONTROL_BAR["background"]),
    ("log_pane", surface.LOG_PANE["background"]),
    ("signal_header", surface.SIGNAL_HEADER["background"]),
    ("signal_pane", surface.SIGNAL_PANE["background"]),
    ("pause_button", surface.PAUSE_BUTTON["background"]),
    ("clear_button", surface.CLEAR_BUTTON["background"]),
]


@pytest.mark.parametrize("name,expected", PAINTED_GROUNDS)
def test_every_part_paints_the_declared_ground(painted, name, expected):
    """A part paints a colour the view model does not declare."""
    host, container, image = painted
    widget = tab_parts(host, container)[name]
    assert colour_at(image, container, widget, ground_point(name, widget)) == expected


def test_the_pause_button_paints_its_checked_ground(painted):
    """The pause button's checked ground is not what the model declares."""
    from qt_pixel import render_widget

    host, container, image = painted
    button = tab_parts(host, container)["pause_button"]
    point = ground_point("pause_button", button)
    assert (
        colour_at(image, container, button, point) == surface.PAUSE_BUTTON["background"]
    )
    button.setChecked(True)
    try:
        checked = render_widget(container, size=RENDER_SIZE)
        assert (
            colour_at(checked, container, button, point)
            == surface.PAUSE_BUTTON["checked_background"]
        )
    finally:
        button.setChecked(False)
    back = render_widget(container, size=RENDER_SIZE)
    assert (
        colour_at(back, container, button, point) == surface.PAUSE_BUTTON["background"]
    )


def test_the_pixel_reader_reports_a_wrong_colour(painted):
    """The pixel check passes whatever the widget painted."""
    from PySide6.QtCore import QPoint

    from qt_pixel import assert_pixel_colour

    host, container, image = painted
    pane = tab_parts(host, container)["log_pane"]
    point = pane.mapTo(container, pane.rect().center())
    assert_pixel_colour(container, point, surface.LOG_PANE["background"])
    with pytest.raises(AssertionError):
        assert_pixel_colour(container, point, "#ffffff")
    with pytest.raises(IndexError):
        colour_at(image, container, pane, QPoint(-5000, -5000))


def test_the_parts_sit_where_the_view_model_orders_them(painted):
    """A part sits somewhere other than the order the model declares."""
    host, container, _image = painted
    parts = tab_parts(host, container)

    def box(widget):
        top_left = widget.mapTo(container, widget.rect().topLeft())
        return top_left.x(), top_left.y(), widget.width(), widget.height()

    bar = box(parts["control_bar"])
    log_pane = box(parts["log_pane"])
    header = box(parts["signal_header"])
    signal_pane = box(parts["signal_pane"])
    pause = box(parts["pause_button"])
    indicator = box(parts["pause_indicator"])
    clear = box(parts["clear_button"])
    assert bar[1] == 0
    assert bar[2] == RENDER_SIZE[0]
    assert log_pane[1] >= bar[1] + bar[3]
    assert header[1] >= log_pane[1] + log_pane[3]
    assert signal_pane[1] == header[1] + header[3]
    assert pause[0] < indicator[0] < clear[0]
    assert clear[0] + clear[2] <= RENDER_SIZE[0]
    assert surface.CONTROL_BAR_ORDER == [
        "pause_button",
        "pause_indicator",
        "stretch",
        "clear_button",
    ]


def test_the_bridge_registers_the_console_tab_method():
    """The renderer cannot reach the Console tab surface over the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 11,
                "method": surface.METHOD,
                "params": {"records": [], "signal_lines": [], "clear": True},
            }
        ),
        registry,
    )
    assert answer["ok"] is True
    assert answer["result"]["tab_title"] == "Console"
    assert answer["result"]["timers"]["drain"]["interval_ms"] == 500


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'console.tab', 'params':"
    " {'records': [{'name': 'a', 'level': 'ERROR', 'message': 'child line',"
    " 'created': 0.0}], 'clear': True}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)


def _run_probe(prelude):
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
    """Reaching the Console tab surface pulled Qt into the backend."""
    answered = _run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["log_pane"]["text"].endswith("[ERROR] a: child line")
    assert result["pause_button"]["text"] == surface.PAUSE_BUTTON_TEXT


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = _run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True
