"""The Qt Activity Log and the Qt-free surface, driven side by side.

A failure means the view model paints a different line, a different
colour, a different pause state or a different health figure than
``StatusLog`` does on the same input.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui import design_system as ds  # noqa: E402
from src.gui.main_tabs import status_log_surface as surface  # noqa: E402
from src.gui.widgets.status_log import StatusLog  # noqa: E402
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

LOG = "log"
LOG_DEFAULT = "log_default"
FORCE = "force"
FORCE_DEFAULT = "force_default"
PAUSE = "pause"
RESUME = "resume"
TOGGLE = "toggle"
FAIL_ON = "fail_on"
FAIL_CLEAR = "fail_clear"

BASE_TIME = datetime(2026, 8, 29, 4, 5, 6)
BASE_SECONDS = 1_000_000.0
STEP_SECONDS = 5.0
SINK_ERROR = "append failed"
POISON = "poison"


class _Clock:
    """The wall clock and the stamp counter both runs read."""

    def __init__(self) -> None:
        self.seconds = BASE_SECONDS
        self.stamps = 0

    def reset(self) -> None:
        self.seconds = BASE_SECONDS
        self.stamps = 0

    def advance(self) -> None:
        self.seconds += STEP_SECONDS

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
    """Pin the wall clock and the stamp so both runs read the same values."""
    import time as time_module

    from src.gui.widgets import status_log as widget_module

    monkeypatch.setattr(time_module, "time", lambda: CLOCK.seconds)
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


class _TracedStatusLog(StatusLog):
    """The widget under test, recording the HTML it is asked to append."""

    def __init__(self):
        super().__init__()
        self.appended: list[str] = []
        self.fail_on: str | None = None

    def append(self, text: str) -> None:
        if self.fail_on is not None and self.fail_on in text:
            raise RuntimeError(SINK_ERROR)
        self.appended.append(text)
        super().append(text)


class _Sink:
    """Records every line the model paints, and fails on a marked one."""

    def __init__(self):
        self.appended: list[str] = []
        self.fail_on: str | None = None

    def __call__(self, html: str) -> None:
        if self.fail_on is not None and self.fail_on in html:
            raise RuntimeError(SINK_ERROR)
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


def _step_trace(appends, scrolls, paused, buffered, returned, health):
    return {
        "appends": list(appends),
        "scrolls": scrolls,
        "paused": paused,
        "buffered": buffered,
        "returned": returned,
        "health": health,
    }


def run_old(script, max_blocks=None):
    """Drive ``StatusLog`` through the script and trace every step."""
    app()
    CLOCK.reset()
    trace = []
    with recorded_scrolls() as scrolls:
        widget = _TracedStatusLog()
        if max_blocks is not None:
            widget.document().setMaximumBlockCount(max_blocks)
        for step in script:
            CLOCK.advance()
            append_mark = len(widget.appended)
            scroll_mark = len(scrolls)
            returned = None
            if step[0] == LOG:
                widget.log(step[1], step[2])
            elif step[0] == LOG_DEFAULT:
                widget.log(step[1])
            elif step[0] == FORCE:
                widget.force_log(step[1], step[2])
            elif step[0] == FORCE_DEFAULT:
                widget.force_log(step[1])
            elif step[0] == PAUSE:
                widget.pause()
            elif step[0] == RESUME:
                widget.resume()
            elif step[0] == TOGGLE:
                returned = widget.toggle_pause()
            elif step[0] == FAIL_ON:
                widget.fail_on = step[1]
            elif step[0] == FAIL_CLEAR:
                widget.fail_on = None
            trace.append(
                _step_trace(
                    widget.appended[append_mark:],
                    len(scrolls) - scroll_mark,
                    widget.is_paused(),
                    len(widget._pause_buffer),
                    returned,
                    widget.health_stats(),
                )
            )
    trace.append({"all_html": list(widget.appended)})
    return trace


def run_new(script, max_blocks=None):
    """Drive the view model through the same script and trace every step."""
    CLOCK.reset()
    sink = _Sink()
    model = surface.StatusLogModel(
        sink=sink,
        max_blocks=surface.MAX_BLOCKS if max_blocks is None else max_blocks,
    )
    trace = []
    for step in script:
        CLOCK.advance()
        append_mark = len(sink.appended)
        scroll_mark = model.scroll_count
        returned = None
        if step[0] == LOG:
            model.log(step[1], step[2])
        elif step[0] == LOG_DEFAULT:
            model.log(step[1])
        elif step[0] == FORCE:
            model.force_log(step[1], step[2])
        elif step[0] == FORCE_DEFAULT:
            model.force_log(step[1])
        elif step[0] == PAUSE:
            model.pause()
        elif step[0] == RESUME:
            model.resume()
        elif step[0] == TOGGLE:
            returned = model.toggle_pause()
        elif step[0] == FAIL_ON:
            sink.fail_on = step[1]
        elif step[0] == FAIL_CLEAR:
            sink.fail_on = None
        trace.append(
            _step_trace(
                sink.appended[append_mark:],
                model.scroll_count - scroll_mark,
                model.is_paused(),
                len(model.pause_buffer),
                returned,
                model.health_stats(),
            )
        )
    trace.append({"all_html": list(sink.appended)})
    return trace


def digest(trace):
    return hashlib.sha256(json.dumps(trace, sort_keys=True).encode("utf-8")).hexdigest()


TRADE_SCRIPT = [
    (LOG, "TRADE NOTIFICATION: FILLED buy 0.5 BTC", "info"),
    (LOG, "TRADE NOTIFICATION: PLACED sell 1 ETH", "info"),
    (LOG, "TRADE NOTIFICATION: SENT limit order", "info"),
    (LOG, "TRADE NOTIFICATION: CANCELLED by venue", "info"),
    (LOG, "TRADE NOTIFICATION:", "info"),
    (LOG, "TRADE NOTIFICATION: PLACED then FILLED", "info"),
    (LOG, "TRADE NOTIFICATION: SENT then PLACED", "info"),
    (LOG, "TRADE NOTIFICATION: FILLED", "error"),
    (LOG, "note: TRADE NOTIFICATION: FILLED not at the start", "info"),
    (LOG, "TRADE NOTIFICATION FILLED without the colon", "info"),
]

WIRE_SCRIPT = [
    (LOG, "WIRE FLOW 12.50 to BTC", "info"),
    (LOG, "WIRE FLOW SKIP dust below minimum", "error"),
    (LOG, "WIRE INCOME 4.00 received", "info"),
    (LOG, "WIRE INCOME PENDING 4.00", "warning"),
    (LOG, "WIRE STACK 3.00 into ETH", "info"),
    (LOG, "WIRE STACK FIRE at entry", "success"),
    (LOG, "wire flow lower case", "info"),
    (LOG, "WIRE something else", "info"),
    (LOG, " WIRE FLOW leading space", "info"),
]

LEVEL_SCRIPT = [
    (LOG, "info line", "info"),
    (LOG, "success line", "success"),
    (LOG, "warning line", "warning"),
    (LOG, "error line", "error"),
    (LOG, "level the map does not name", "critical"),
    (LOG, "empty level", ""),
    (LOG, "level is none", None),
    (LOG_DEFAULT, "no level given at all"),
    (LOG, "", "info"),
    (LOG, "a & b", "info"),
    (LOG, "a < b > c", "info"),
    (LOG, "⚡ unicode arrow →", "info"),
]

PAUSE_SCRIPT = [
    (LOG, "before the pause", "info"),
    (PAUSE,),
    (LOG, "held one", "info"),
    (LOG, "TRADE NOTIFICATION: FILLED held two", "info"),
    (FORCE, "forced through the pause", "error"),
    (FORCE_DEFAULT, "forced with the default level"),
    (RESUME,),
    (LOG, "after the resume", "info"),
    (RESUME,),
]

TOGGLE_SCRIPT = [
    (TOGGLE,),
    (LOG, "held while paused", "info"),
    (TOGGLE,),
    (LOG, "painted again", "info"),
    (TOGGLE,),
    (TOGGLE,),
    (PAUSE,),
    (PAUSE,),
    (LOG, "held once", "info"),
    (RESUME,),
]

BUFFER_CAP_SCRIPT = [
    (LOG, "painted first", "info"),
    (PAUSE,),
    (LOG, "held one", "info"),
    (LOG, "held two", "info"),
    (LOG, "dropped one", "info"),
    (LOG, "dropped two", "info"),
    (RESUME,),
    (LOG, "after the resume", "info"),
]

FAIL_SCRIPT = [
    (LOG, "painted first", "info"),
    (FAIL_ON, POISON),
    (LOG, "poison one", "error"),
    (LOG, "poison two", "info"),
    (LOG, "healthy line", "info"),
    (FAIL_CLEAR,),
    (LOG, "poison three now healthy", "info"),
    (FAIL_ON, POISON),
    (PAUSE,),
    (LOG, "poison held", "info"),
    (FORCE, "poison forced", "warning"),
    (RESUME,),
]

BLOCK_CAP_SCRIPT = [
    (LOG, "one", "info"),
    (LOG, "two", "info"),
    (LOG, "three", "info"),
    (LOG, "four", "info"),
    (LOG, "five", "info"),
    (LOG, "six", "info"),
]

EMPTY_SCRIPT = [
    (RESUME,),
    (PAUSE,),
    (RESUME,),
]

SCRIPTS = {
    "trade": (TRADE_SCRIPT, None),
    "wire": (WIRE_SCRIPT, None),
    "levels": (LEVEL_SCRIPT, None),
    "pause": (PAUSE_SCRIPT, None),
    "toggle": (TOGGLE_SCRIPT, None),
    "buffer_cap": (BUFFER_CAP_SCRIPT, None),
    "fail": (FAIL_SCRIPT, None),
    "block_cap": (BLOCK_CAP_SCRIPT, 4),
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
    assert all("health" in step for step in old[:-1])
    if name == "empty":
        assert old[-1]["all_html"] == []
        return
    assert any(step["appends"] for step in old[:-1])
    assert any(step["scrolls"] for step in old[:-1])
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
        ds.CARD_METRIC_LABEL,
        ds.SUCCESS,
        ds.WARNING,
        ds.PRIMARY,
        ds.ERROR,
        ds.MAIN_BADGE_MAGENTA,
        ds.STATE_PENDING,
        ds.TEXT_HIGH,
    ):
        assert f"color:{token}" in painted, token
    assert "font-size:14px" in painted
    assert "font-size:12px" in painted
    assert "font-style:italic;" in painted
    assert "⚡ " in painted
    assert "buffered message(s) above" in painted


def test_every_style_kind_is_driven():
    """A branch of the style rule was never reached by any script."""
    reached = set()
    for script, _ in SCRIPTS.values():
        for step in script:
            if step[0] in (LOG, FORCE):
                reached.add(surface.line_style(step[1], step[2])["kind"])
            elif step[0] in (LOG_DEFAULT, FORCE_DEFAULT):
                reached.add(surface.line_style(step[1])["kind"])
    assert reached == {
        surface.KIND_TRADE,
        surface.KIND_WIRE_FLOW,
        surface.KIND_WIRE_STACK,
        surface.KIND_PLAIN,
    }


def test_pause_buffer_cap_drops_the_newest_on_both_sides():
    """A full pause buffer kept a different message on one of the two sides."""
    app()
    CLOCK.reset()
    widget = _TracedStatusLog()
    widget._pause_buffer_cap = 2
    for step in BUFFER_CAP_SCRIPT:
        CLOCK.advance()
        if step[0] == LOG:
            widget.log(step[1], step[2])
        elif step[0] == PAUSE:
            widget.pause()
        elif step[0] == RESUME:
            widget.resume()
    CLOCK.reset()
    sink = _Sink()
    model = surface.StatusLogModel(sink=sink, pause_buffer_cap=2)
    for step in BUFFER_CAP_SCRIPT:
        CLOCK.advance()
        if step[0] == LOG:
            model.log(step[1], step[2])
        elif step[0] == PAUSE:
            model.pause()
        elif step[0] == RESUME:
            model.resume()
    assert widget.appended == sink.appended
    assert widget.health_stats() == model.health_stats()
    painted = "".join(widget.appended)
    assert "held two" in painted
    assert "dropped one" not in painted
    assert "dropped two" not in painted
    assert "2 buffered message(s) above" in painted


def test_render_error_is_counted_and_logged_the_same(capture_log):
    """A failed paint left a different trace on one of the two sides."""
    app()
    CLOCK.reset()
    widget = _TracedStatusLog()
    widget.fail_on = POISON
    with capture_log("acervator.gui", logging.ERROR) as records:
        widget.log("poison one", "error")
        old_records = [record.getMessage() for record in records]
    CLOCK.reset()
    sink = _Sink()
    sink.fail_on = POISON
    model = surface.StatusLogModel(sink=sink)
    with capture_log("acervator.gui", logging.ERROR) as records:
        model.log("poison one", "error")
        new_records = [record.getMessage() for record in records]
    assert len(old_records) == 1
    assert old_records == new_records
    assert "StatusLog._render exception (#1)" in old_records[0]
    assert "message='poison one' level='error'" in old_records[0]
    assert widget.health_stats() == model.health_stats()
    assert widget._render_errors == 1
    assert widget._last_render_error == f"RuntimeError: {SINK_ERROR}"
    assert model.last_render_error == widget._last_render_error
    assert widget._last_render_error_time == model.last_render_error_time


def test_a_failing_logger_is_swallowed_on_both_sides(monkeypatch):
    """A logger that raises took the message down with it on one side."""
    app()

    def raising(*_args, **_kwargs):
        raise OSError("logger down")

    monkeypatch.setattr(surface.logger, "error", raising)
    CLOCK.reset()
    widget = _TracedStatusLog()
    widget.fail_on = POISON
    widget.log("poison one", "error")
    CLOCK.reset()
    sink = _Sink()
    sink.fail_on = POISON
    model = surface.StatusLogModel(sink=sink)
    model.log("poison one", "error")
    assert widget._render_errors == 1
    assert widget.health_stats() == model.health_stats()


def test_the_two_sides_share_one_logger_channel():
    """The surface reports render failures on a channel the pane does not."""
    from src.gui.widgets import status_log as widget_module

    assert surface.logger is widget_module.logger
    assert surface.logger.name == "acervator.gui"


def test_constructor_properties_match_the_widget():
    """A widget property drifted from the value the surface reports."""
    app()
    widget = StatusLog()
    assert surface.WIDGET == {
        "accessible_name": widget.accessibleName(),
        "read_only": widget.isReadOnly(),
        "maximum_height_px": widget.maximumHeight(),
        "placeholder_text": widget.placeholderText(),
        "maximum_block_count": widget.document().maximumBlockCount(),
    }
    assert surface.WIDGET["accessible_name"] == "Status Log"
    assert surface.WIDGET["maximum_height_px"] == 150
    assert surface.WIDGET["placeholder_text"] == "Activity log..."
    assert surface.WIDGET["maximum_block_count"] == 5000
    assert surface.PAUSE_BUFFER_CAP == widget._pause_buffer_cap == 2000
    assert widget.is_paused() is False
    assert surface.StatusLogModel().is_paused() is False


def test_health_keys_match_the_widget_exactly():
    """The watchdog reads a key one side does not report."""
    app()
    CLOCK.reset()
    widget = StatusLog()
    CLOCK.reset()
    model = surface.StatusLogModel()
    old = widget.health_stats()
    new = model.health_stats()
    assert list(old) == list(new)
    assert old == new
    assert list(old) == [
        "paused",
        "pause_buffer_size",
        "last_render_age_sec",
        "total_renders",
        "render_errors",
        "last_render_error",
        "document_blocks",
    ]


def test_health_age_tracks_the_clock_on_both_sides():
    """The render age froze on one side, so a stalled log would read healthy."""
    app()
    CLOCK.reset()
    widget = StatusLog()
    CLOCK.reset()
    model = surface.StatusLogModel()
    CLOCK.advance()
    assert widget.health_stats()["last_render_age_sec"] == STEP_SECONDS
    assert model.health_stats()["last_render_age_sec"] == STEP_SECONDS
    widget.log("fresh")
    model.log("fresh")
    assert widget.health_stats()["last_render_age_sec"] == 0.0
    assert model.health_stats()["last_render_age_sec"] == 0.0


METHOD_MAP = {
    "is_paused": "is_paused",
    "pause": "pause",
    "resume": "resume",
    "toggle_pause": "toggle_pause",
    "log": "log",
    "force_log": "force_log",
    "health_stats": "health_stats",
    "_render": "render",
    "_render_safe": "render_line",
}


def test_every_widget_method_has_a_counterpart():
    """A method exists on one side and nowhere on the other."""
    widget_methods = {
        name
        for name, value in vars(StatusLog).items()
        if callable(value) and name != "__init__"
    }
    assert widget_methods == set(METHOD_MAP)
    for target in METHOD_MAP.values():
        assert callable(getattr(surface.StatusLogModel, target))


def test_rgb_matches_qcolor_on_every_token():
    """The Qt-free colour split disagrees with QColor on a token."""
    from PySide6.QtGui import QColor

    tokens = [
        surface.TIMESTAMP_COLOR,
        surface.WIRE_FLOW_COLOR,
        surface.WIRE_STACK_COLOR,
        surface.RESUME_MARKER_COLOR,
        surface.STAGE_DEFAULT_COLOR,
        surface.DEFAULT_LEVEL_COLOR,
        *[token for _stage, token in surface.STAGE_COLORS],
        *surface.LEVEL_COLORS.values(),
    ]
    assert surface.rgb(surface.TIMESTAMP_COLOR) == (136, 136, 136)
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
    widget_text = (REPO_ROOT / "src/gui/widgets/status_log.py").read_text(
        encoding="utf-8"
    )
    surface_text = (REPO_ROOT / "src/gui/main_tabs/status_log_surface.py").read_text(
        encoding="utf-8"
    )
    assert widget_text.count(".connect(") == 0
    assert surface_text.count(".connect(") == 0


PIXEL_MESSAGES = [
    ("TRADE NOTIFICATION: FILLED buy", "info"),
    ("TRADE NOTIFICATION: PLACED sell", "info"),
    ("TRADE NOTIFICATION: SENT order", "info"),
    ("TRADE NOTIFICATION: CANCELLED", "info"),
    ("WIRE FLOW 12.50 to BTC", "info"),
    ("WIRE INCOME 4.00 received", "info"),
    ("WIRE STACK 3.00 into ETH", "success"),
    ("plain info", "info"),
    ("plain success", "success"),
    ("plain warning", "warning"),
    ("plain error", "error"),
    ("unnamed level", "critical"),
]
PIXEL_SIZE = (520, 420)


def widget_painted_by_the_widget():
    CLOCK.reset()
    widget = StatusLog()
    widget.setMaximumHeight(PIXEL_SIZE[1])
    for message, level in PIXEL_MESSAGES:
        widget.log(message, level)
    widget.pause()
    widget.log("held one", "info")
    widget.log("held two", "warning")
    widget.resume()
    return widget


def model_lines():
    CLOCK.reset()
    sink = _Sink()
    model = surface.StatusLogModel(sink=sink)
    for message, level in PIXEL_MESSAGES:
        model.log(message, level)
    model.pause()
    model.log("held one", "info")
    model.log("held two", "warning")
    model.resume()
    return sink.appended


def widget_painted_by_the_model(lines):
    widget = StatusLog()
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


def test_the_pixel_check_reports_a_changed_colour():
    """The image comparison passes whatever the second side paints."""
    app()
    lines = model_lines()
    altered = [line.replace(ds.SUCCESS, ds.ERROR) for line in lines]
    assert altered != lines
    assert_pictures_differ(
        old_side=render_offscreen(widget_painted_by_the_widget(), PIXEL_SIZE),
        new_side=render_offscreen(widget_painted_by_the_model(altered), PIXEL_SIZE),
    )


def test_the_pixel_check_reports_a_changed_size():
    """The image comparison cannot see a font size change."""
    app()
    lines = model_lines()
    altered = [line.replace("font-size:12px", "font-size:13px") for line in lines]
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


def test_a_block_level_tag_in_a_message_splits_the_qt_document():
    """The one input where the pane and the model count blocks differently."""
    app()
    CLOCK.reset()
    widget = StatusLog()
    widget.log("one<p>two</p>", "info")
    CLOCK.reset()
    model = surface.StatusLogModel()
    model.log("one<p>two</p>", "info")
    assert widget.health_stats()["document_blocks"] == 2
    assert model.health_stats()["document_blocks"] == 1
    CLOCK.reset()
    plain = StatusLog()
    plain.log("one<br>two", "info")
    assert plain.health_stats()["document_blocks"] == 1


def test_view_model_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    model = surface.StatusLogModel()
    payload = surface.build_view_model(
        model,
        [
            {"message": "WIRE FLOW 1.00 to BTC", "level": "info"},
            {"message": "plain error", "level": "error"},
        ],
    )
    encoded = json.loads(json.dumps(payload))
    assert encoded["document"]["lines"][0]["color"] == ds.MAIN_BADGE_MAGENTA
    assert encoded["document"]["lines"][1]["color"] == ds.ERROR
    assert encoded["widget"]["maximum_height_px"] == 150
    assert encoded["timestamp_color"] == [136, 136, 136]
    assert encoded["buffer_cap"] == surface.PAUSE_BUFFER_CAP
    assert encoded["health"]["total_renders"] == 2
    assert encoded["document_blocks"] == 2


def test_view_model_pause_resume_and_force():
    """The batch path holds, drains or forces a line the pane would not."""
    model = surface.StatusLogModel()
    surface.build_view_model(model, [{"message": "first"}])
    held = surface.build_view_model(model, [{"message": "held"}], paused=True)
    assert held["document"]["lines"] == []
    assert held["buffered"] == 1
    forced = surface.build_view_model(model, [{"message": "forced", "force": True}])
    assert [line["message"] for line in forced["document"]["lines"]] == ["forced"]
    assert forced["paused"] is True
    drained = surface.build_view_model(model, [{"message": "after"}], paused=False)
    messages = [line["message"] for line in drained["document"]["lines"]]
    assert messages[0] == "held"
    assert "1 buffered message(s) above" in messages[1]
    assert messages[2] == "after"
    toggled = surface.build_view_model(model, [], toggle=True)
    assert toggled["paused"] is True
    assert surface.build_view_model(model, [], toggle=True)["paused"] is False


def test_view_model_skips_a_message_it_cannot_read():
    """A message that cannot be read raised instead of being skipped."""

    class _Raising:
        def get(self, _key, _default=None):
            raise ValueError("unreadable message")

    model = surface.StatusLogModel()
    payload = surface.build_view_model(model, [_Raising()])
    assert payload["document"]["lines"] == []


def test_bridge_registers_the_status_log_method():
    """The renderer cannot reach the Activity Log surface through the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 11,
                "method": surface.METHOD,
                "params": {"messages": [{"message": "bridge line", "level": "error"}]},
            }
        ),
        registry,
    )
    assert answer["ok"] is True
    line = answer["result"]["document"]["lines"][0]
    assert line["message"] == "bridge line"
    assert (line["r"], line["g"], line["b"]) == surface.rgb(ds.ERROR)


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'status_log.lines', 'params':"
    " {'messages': [{'message': 'WIRE STACK child', 'level': 'info'}]}}),"
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
    """Reaching the Activity Log surface pulled Qt into the backend process."""
    answered = run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    line = answered["frame"]["result"]["document"]["lines"][0]
    assert line["kind"] == surface.KIND_WIRE_STACK
    assert [line["r"], line["g"], line["b"]] == list(surface.rgb(ds.STATE_PENDING))


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True
