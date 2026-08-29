"""The Qt Notification Spool and the Qt-free surface, driven side by side.

A failure means the view model paints a different line, a different
colour, a different block count or a different scroll than
``NotificationSpool`` does on the same input.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui import design_system as ds
from src.gui.main_tabs import notification_spool_surface as surface
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
)
from src.gui.widgets.notification_spool import NotificationSpool

REPO_ROOT = Path(__file__).resolve().parents[1]

NOTIFY = "notify"
NOTIFY_DEFAULT = "notify_default"

BASE_TIME = datetime(2026, 8, 29, 4, 5, 6)


class _Clock:
    """The stamp counter both runs read, so one stamp serves both sides."""

    def __init__(self) -> None:
        self.stamps = 0

    def reset(self) -> None:
        self.stamps = 0

    def next_stamp(self) -> datetime:
        moment = BASE_TIME + timedelta(seconds=self.stamps)
        self.stamps += 1
        return moment


CLOCK = _Clock()


class _FrozenDateTime:
    @staticmethod
    def now() -> datetime:
        return CLOCK.next_stamp()


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    """Pin the stamp so both runs read the same timestamps."""
    from src.gui.widgets import notification_spool as widget_module

    monkeypatch.setattr(widget_module, "datetime", _FrozenDateTime)
    monkeypatch.setattr(surface, "datetime", _FrozenDateTime)
    CLOCK.reset()
    yield
    CLOCK.reset()


def app():
    """The process application object every render and widget needs."""
    from qt_pixel import ensure_app

    return ensure_app()


def render_offscreen(widget, size):
    from qt_pixel import render_widget

    return render_widget(widget, size)


class _TracedNotificationSpool(NotificationSpool):
    """The widget under test, recording the HTML it is asked to append."""

    def __init__(self):
        super().__init__()
        self.appended: list[str] = []

    def append(self, text: str) -> None:
        self.appended.append(text)
        super().append(text)


class _Sink:
    """Records every line the model paints."""

    def __init__(self):
        self.appended: list[str] = []

    def __call__(self, html: str) -> None:
        self.appended.append(html)


@contextmanager
def recorded_scrolls():
    """Record every jump to the newest line the Qt widget performs."""
    from PySide6.QtWidgets import QScrollBar

    calls: list[int] = []
    original = QScrollBar.setValue

    def recording(self, value):
        calls.append(value)
        original(self, value)

    QScrollBar.setValue = recording
    try:
        yield calls
    finally:
        QScrollBar.setValue = original


def _step_trace(appends, scrolls, blocks):
    return {
        "appends": list(appends),
        "scrolls": scrolls,
        "document_blocks": blocks,
    }


def run_old(script, max_blocks=None):
    """Drive ``NotificationSpool`` through the script and trace every step."""
    app()
    CLOCK.reset()
    trace = []
    with recorded_scrolls() as scrolls:
        widget = _TracedNotificationSpool()
        if max_blocks is not None:
            widget.document().setMaximumBlockCount(max_blocks)
        for step in script:
            append_mark = len(widget.appended)
            scroll_mark = len(scrolls)
            if step[0] == NOTIFY:
                widget.notify(step[1], step[2])
            elif step[0] == NOTIFY_DEFAULT:
                widget.notify(step[1])
            trace.append(
                _step_trace(
                    widget.appended[append_mark:],
                    len(scrolls) - scroll_mark,
                    widget.document().blockCount(),
                )
            )
    trace.append({"all_html": list(widget.appended)})
    return trace


def run_new(script, max_blocks=None):
    """Drive the view model through the same script and trace every step."""
    CLOCK.reset()
    sink = _Sink()
    model = surface.NotificationSpoolModel(
        sink=sink,
        max_blocks=surface.MAX_BLOCKS if max_blocks is None else max_blocks,
    )
    trace = []
    for step in script:
        append_mark = len(sink.appended)
        scroll_mark = model.scroll_count
        if step[0] == NOTIFY:
            model.notify(step[1], step[2])
        elif step[0] == NOTIFY_DEFAULT:
            model.notify(step[1])
        trace.append(
            _step_trace(
                sink.appended[append_mark:],
                model.scroll_count - scroll_mark,
                model.document_blocks(),
            )
        )
    trace.append({"all_html": list(sink.appended)})
    return trace


def digest(trace):
    return hashlib.sha256(json.dumps(trace, sort_keys=True).encode("utf-8")).hexdigest()


LEVEL_SCRIPT = [
    (NOTIFY, "market open", "info"),
    (NOTIFY, "fold complete", "success"),
    (NOTIFY, "spread widening", "warning"),
    (NOTIFY, "order rejected", "error"),
    (NOTIFY, "BTC 64000.00", "market"),
    (NOTIFY, "level the map does not name", "critical"),
    (NOTIFY_DEFAULT, "no level given at all"),
]

ODD_LEVEL_SCRIPT = [
    (NOTIFY, "empty level", ""),
    (NOTIFY, "level is none", None),
    (NOTIFY, "level is a number", 0),
    (NOTIFY, "level is uppercase", "INFO"),
    (NOTIFY, "level has a leading space", " info"),
    (NOTIFY, "level is a bool", True),
]

MESSAGE_SCRIPT = [
    (NOTIFY, "", "info"),
    (NOTIFY, " ", "info"),
    (NOTIFY, "a & b", "info"),
    (NOTIFY, "a < b > c", "success"),
    (NOTIFY, 'a "quoted" word', "warning"),
    (NOTIFY, "unicode arrow → and bolt ⚡", "market"),
    (NOTIFY, "a" * 400, "error"),
    (NOTIFY, "line one\nline two", "info"),
]

BLOCK_CAP_SCRIPT = [
    (NOTIFY, "one", "info"),
    (NOTIFY, "two", "success"),
    (NOTIFY, "three", "warning"),
    (NOTIFY, "four", "error"),
    (NOTIFY, "five", "market"),
    (NOTIFY, "six", "critical"),
]

SINGLE_SCRIPT = [
    (NOTIFY, "the only notification", "market"),
]

EMPTY_SCRIPT: list[tuple] = []

SCRIPTS = {
    "levels": (LEVEL_SCRIPT, None),
    "odd_levels": (ODD_LEVEL_SCRIPT, None),
    "messages": (MESSAGE_SCRIPT, None),
    "block_cap": (BLOCK_CAP_SCRIPT, 4),
    "single": (SINGLE_SCRIPT, None),
    "empty": (EMPTY_SCRIPT, None),
}


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_old_and_new_traces_are_identical(name):
    """A step of the script paints something the other side does not."""
    script, max_blocks = SCRIPTS[name]
    old = run_old(script, max_blocks)
    new = run_new(script, max_blocks)
    assert new == old
    assert digest(new) == digest(old)


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_trace_is_not_empty(name):
    """The comparison passed by measuring nothing."""
    script, max_blocks = SCRIPTS[name]
    old = run_old(script, max_blocks)
    assert len(old) == len(script) + 1
    if name == "empty":
        assert old[-1]["all_html"] == []
        return
    assert all(len(step["appends"]) == 1 for step in old[:-1])
    assert all(step["scrolls"] >= 1 for step in old[:-1])
    assert old[-1]["all_html"] != []


def all_old_html():
    """Every HTML string the widget appended across every script."""
    painted = []
    for script, max_blocks in SCRIPTS.values():
        painted.extend(run_old(script, max_blocks)[-1]["all_html"])
    return painted


def test_every_colour_rule_reaches_the_widget_output():
    """A colour rule was never driven, so its parity was never compared."""
    painted = "".join(all_old_html())
    for token in (
        ds.TEXT_PLACEHOLDER,
        ds.PRIMARY,
        ds.SUCCESS,
        ds.WARNING,
        ds.ERROR,
        ds.STATE_MARKET,
        ds.TEXT_HIGH,
    ):
        assert f"color:{token}" in painted, token


def test_every_level_branch_is_driven():
    """A branch of the colour rule was never reached by any script."""
    reached = set()
    for script, _ in SCRIPTS.values():
        for step in script:
            if step[0] == NOTIFY:
                reached.add(surface.level_color(step[2]))
            else:
                reached.add(surface.level_color(surface.DEFAULT_LEVEL))
    assert reached == {
        ds.PRIMARY,
        ds.SUCCESS,
        ds.WARNING,
        ds.ERROR,
        ds.STATE_MARKET,
        ds.TEXT_HIGH,
    }


def test_the_default_level_is_the_info_level():
    """The omitted-level default drifted from the level the pane assumes."""
    app()
    CLOCK.reset()
    omitted = _TracedNotificationSpool()
    omitted.notify("no level")
    CLOCK.reset()
    explicit = _TracedNotificationSpool()
    explicit.notify("no level", "info")
    assert omitted.appended == explicit.appended
    assert surface.DEFAULT_LEVEL == "info"
    assert surface.level_color(surface.DEFAULT_LEVEL) == ds.PRIMARY


def test_constructor_properties_match_the_widget():
    """A widget property drifted from the value the surface reports."""
    app()
    widget = NotificationSpool()
    assert surface.WIDGET == {
        "accessible_name": widget.accessibleName(),
        "read_only": widget.isReadOnly(),
        "maximum_height_px": widget.maximumHeight(),
        "placeholder_text": widget.placeholderText(),
        "maximum_block_count": widget.document().maximumBlockCount(),
    }
    assert surface.WIDGET["accessible_name"] == "Notification Spool"
    assert surface.WIDGET["read_only"] is True
    assert surface.WIDGET["maximum_height_px"] == 100
    assert surface.WIDGET["placeholder_text"] == (
        "Market status and bot notifications..."
    )
    assert surface.WIDGET["maximum_block_count"] == 0
    assert surface.TIMESTAMP_FORMAT == "%H:%M:%S"


def test_an_empty_pane_reports_one_block_on_both_sides():
    """The empty state counted a different number of blocks."""
    app()
    widget = NotificationSpool()
    model = surface.NotificationSpoolModel()
    assert widget.document().blockCount() == 1
    assert model.document_blocks() == 1
    assert model.lines == []
    assert widget.toPlainText() == ""


def test_the_document_cap_drops_the_oldest_on_both_sides():
    """A full document kept a different set of lines on one of the two sides."""
    app()
    CLOCK.reset()
    widget = NotificationSpool()
    widget.document().setMaximumBlockCount(4)
    for step in BLOCK_CAP_SCRIPT:
        widget.notify(step[1], step[2])
    CLOCK.reset()
    model = surface.NotificationSpoolModel(max_blocks=4)
    for step in BLOCK_CAP_SCRIPT:
        model.notify(step[1], step[2])
    assert widget.toPlainText().splitlines() == [
        f"{line['stamp']} {line['message']}" for line in model.lines
    ]
    assert [line["message"] for line in model.lines] == [
        "three",
        "four",
        "five",
        "six",
    ]


METHOD_MAP = {"notify": "notify"}


def test_every_widget_method_has_a_counterpart():
    """A method exists on one side and nowhere on the other."""
    widget_methods = {
        name
        for name, value in vars(NotificationSpool).items()
        if callable(value) and name != "__init__"
    }
    assert widget_methods == set(METHOD_MAP)
    for target in METHOD_MAP.values():
        assert callable(getattr(surface.NotificationSpoolModel, target))


def test_rgb_matches_qcolor_on_every_token():
    """The Qt-free colour split disagrees with QColor on a token."""
    from PySide6.QtGui import QColor

    tokens = [
        surface.TIMESTAMP_COLOR,
        surface.DEFAULT_LEVEL_COLOR,
        *surface.LEVEL_COLORS.values(),
    ]
    assert surface.rgb(surface.LEVEL_COLORS["market"]) == (136, 204, 255)
    assert surface.rgb(surface.LEVEL_COLORS["info"]) == (0, 255, 204)
    assert surface.rgb(surface.LEVEL_COLORS["error"]) == (255, 51, 102)
    assert surface.rgb(surface.TIMESTAMP_COLOR) == (85, 85, 85)
    assert surface.rgb("#abc") == (
        QColor("#abc").red(),
        QColor("#abc").green(),
        QColor("#abc").blue(),
    )
    for token in tokens:
        painted = QColor(token)
        assert surface.rgb(token) == (
            painted.red(),
            painted.green(),
            painted.blue(),
        )


def test_neither_file_connects_a_signal():
    """A signal connection appeared on one side and not the other."""
    widget_text = (REPO_ROOT / "src/gui/widgets/notification_spool.py").read_text(
        encoding="utf-8"
    )
    surface_text = (
        REPO_ROOT / "src/gui/main_tabs/notification_spool_surface.py"
    ).read_text(encoding="utf-8")
    assert widget_text.count(".connect(") == 0
    assert surface_text.count(".connect(") == 0


PIXEL_MESSAGES = [
    ("market open 09:30", "info"),
    ("fold complete on BTC", "success"),
    ("spread widening on ETH", "warning"),
    ("order rejected by venue", "error"),
    ("BTC 64000.00 +1.2%", "market"),
    ("level the map does not name", "critical"),
]
PIXEL_SIZE = (520, 220)


def widget_painted_by_the_widget():
    CLOCK.reset()
    widget = NotificationSpool()
    widget.setMaximumHeight(PIXEL_SIZE[1])
    for message, level in PIXEL_MESSAGES:
        widget.notify(message, level)
    return widget


def model_lines():
    CLOCK.reset()
    sink = _Sink()
    model = surface.NotificationSpoolModel(sink=sink)
    for message, level in PIXEL_MESSAGES:
        model.notify(message, level)
    return sink.appended


def widget_painted_by_the_model(lines):
    widget = NotificationSpool()
    widget.setMaximumHeight(PIXEL_SIZE[1])
    for html in lines:
        widget.append(html)
    return widget


def test_the_two_sides_render_the_same_pixels():
    """The page paints a colour, a size or a position the pane does not."""
    app()
    assert_pictures_match(
        old_side=render_offscreen(widget_painted_by_the_widget(), PIXEL_SIZE),
        new_side=render_offscreen(
            widget_painted_by_the_model(model_lines()), PIXEL_SIZE
        ),
    )


def test_the_pixel_check_reports_a_changed_message_colour():
    """The image comparison passes whatever the second side paints."""
    app()
    lines = model_lines()
    altered = [line.replace(ds.SUCCESS, ds.ERROR) for line in lines]
    assert altered != lines
    assert_pictures_differ(
        old_side=render_offscreen(widget_painted_by_the_widget(), PIXEL_SIZE),
        new_side=render_offscreen(widget_painted_by_the_model(altered), PIXEL_SIZE),
    )


def test_the_pixel_check_reports_a_changed_timestamp_colour():
    """The image comparison cannot see the timestamp change colour."""
    app()
    lines = model_lines()
    altered = [line.replace(ds.TEXT_PLACEHOLDER, ds.TEXT_HIGH) for line in lines]
    assert altered != lines
    assert_pictures_differ(
        old_side=render_offscreen(widget_painted_by_the_widget(), PIXEL_SIZE),
        new_side=render_offscreen(widget_painted_by_the_model(altered), PIXEL_SIZE),
    )


def test_the_pixel_check_reports_a_changed_order():
    """The image comparison cannot see two lines swapped."""
    app()
    lines = model_lines()
    swapped = list(lines)
    swapped[0], swapped[1] = swapped[1], swapped[0]
    assert swapped != lines
    assert_pictures_differ(
        old_side=render_offscreen(widget_painted_by_the_widget(), PIXEL_SIZE),
        new_side=render_offscreen(widget_painted_by_the_model(swapped), PIXEL_SIZE),
    )


def test_the_pixel_check_reports_a_dropped_space_after_the_stamp():
    """The image comparison cannot see the stamp separator disappear."""
    app()
    lines = model_lines()
    altered = [line.replace("</span> <span", "</span><span") for line in lines]
    assert altered != lines
    assert_pictures_differ(
        old_side=render_offscreen(widget_painted_by_the_widget(), PIXEL_SIZE),
        new_side=render_offscreen(widget_painted_by_the_model(altered), PIXEL_SIZE),
    )


def test_a_block_level_tag_in_a_message_splits_the_qt_document():
    """The one input where the pane and the model count blocks differently."""
    app()
    CLOCK.reset()
    widget = NotificationSpool()
    widget.notify("one<p>two</p>", "info")
    CLOCK.reset()
    model = surface.NotificationSpoolModel()
    model.notify("one<p>two</p>", "info")
    assert widget.document().blockCount() == 2
    assert model.document_blocks() == 1
    CLOCK.reset()
    plain = NotificationSpool()
    plain.notify("one<br>two", "info")
    assert plain.document().blockCount() == 1


def test_view_model_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    model = surface.NotificationSpoolModel()
    payload = surface.build_view_model(
        model,
        [
            {"message": "BTC 64000.00", "level": "market"},
            {"message": "order rejected", "level": "error"},
            {"message": "no level given"},
        ],
    )
    encoded = json.loads(json.dumps(payload))
    lines = encoded["document"]["lines"]
    assert [line["color"] for line in lines] == [
        ds.STATE_MARKET,
        ds.ERROR,
        ds.PRIMARY,
    ]
    assert [line["message"] for line in lines] == [
        "BTC 64000.00",
        "order rejected",
        "no level given",
    ]
    assert encoded["widget"]["maximum_height_px"] == 100
    assert encoded["timestamp_color"] == [85, 85, 85]
    assert encoded["level_colors"]["market"] == [136, 204, 255]
    assert encoded["default_level_color"] == list(surface.rgb(ds.TEXT_HIGH))
    assert encoded["document_blocks"] == 3


def test_view_model_returns_only_the_new_lines():
    """A second call repainted lines the pane had already painted."""
    model = surface.NotificationSpoolModel()
    first = surface.build_view_model(model, [{"message": "one", "level": "info"}])
    second = surface.build_view_model(model, [{"message": "two", "level": "info"}])
    assert [line["message"] for line in first["document"]["lines"]] == ["one"]
    assert [line["message"] for line in second["document"]["lines"]] == ["two"]
    assert second["document_blocks"] == 2
    empty = surface.build_view_model(model, [])
    assert empty["document"]["lines"] == []
    assert empty["document_blocks"] == 2


def test_view_model_skips_a_message_it_cannot_read(capture_log):
    """A message that cannot be read raised instead of being skipped."""

    class _Raising:
        def get(self, _key, _default=None):
            raise ValueError("unreadable message")

    model = surface.NotificationSpoolModel()
    with capture_log(surface.logger.name) as records:
        payload = surface.build_view_model(
            model, [_Raising(), {"message": "survivor", "level": "info"}]
        )
    assert [line["message"] for line in payload["document"]["lines"]] == ["survivor"]
    assert [record.getMessage() for record in records] == [
        "notification spool message skipped: unreadable message"
    ]


def test_bridge_registers_the_notification_spool_method():
    """The renderer cannot reach the Notification Spool through the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 12,
                "method": surface.METHOD,
                "params": {"messages": [{"message": "bridge line", "level": "market"}]},
            }
        ),
        registry,
    )
    assert answer["ok"] is True
    line = answer["result"]["document"]["lines"][0]
    assert line["message"] == "bridge line"
    assert (line["r"], line["g"], line["b"]) == surface.rgb(ds.STATE_MARKET)


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'notification_spool.lines', 'params':"
    " {'messages': [{'message': 'BTC 64000.00', 'level': 'market'}]}}),"
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
    """Reaching the Notification Spool pulled Qt into the backend process."""
    answered = run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    line = answered["frame"]["result"]["document"]["lines"][0]
    assert line["color"] == ds.STATE_MARKET
    assert [line["r"], line["g"], line["b"]] == list(surface.rgb(ds.STATE_MARKET))


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True
