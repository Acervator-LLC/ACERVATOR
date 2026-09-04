"""The Qt console handler and the Qt-free surface, driven side by side.

A failure means the view model paints a different line, a different
colour, a different pane text or a different pause state than
``_QtLogHandler`` does on the same input.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest

from src.gui import design_system as ds
from src.gui.main_tabs import console_log_surface as surface
from src.gui.main_tabs.console_log_handler import _QtLogHandler

REPO_ROOT = Path(__file__).resolve().parents[1]

LOG = "log"
PAUSE = "pause"
SCROLL = "scroll"


class _FakeCursor:
    """Records what the handler would have inserted into the pane."""

    class MoveOperation:
        End = "End"

    def __init__(self, pane):
        self._pane = pane

    def movePosition(self, where):
        self._pane.moves.append(where)

    def insertText(self, text, fmt):
        colour = fmt.foreground().color()
        self._pane.text += text
        self._pane.inserts.append((text, colour.red(), colour.green(), colour.blue()))


class _FakeDocument:
    def __init__(self, pane):
        self._pane = pane

    def isEmpty(self):
        return self._pane.text == ""


class _FakeScrollBar:
    def __init__(self):
        self._value = 0
        self._maximum = 0
        self.set_calls = []

    def value(self):
        return self._value

    def maximum(self):
        return self._maximum

    def setValue(self, value):
        self._value = value
        self.set_calls.append(value)


class _FakePane:
    """Stands in for the QPlainTextEdit the handler paints."""

    def __init__(self):
        self.text = ""
        self.moves = []
        self.inserts = []
        self._bar = _FakeScrollBar()

    def textCursor(self):
        return _FakeCursor(self)

    def document(self):
        return _FakeDocument(self)

    def verticalScrollBar(self):
        return self._bar


def _record(levelname, text):
    record = logging.LogRecord(
        name="acervator.parity",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=text,
        args=(),
        exc_info=None,
    )
    record.levelname = levelname
    return record


def run_old(script, buffer_max=surface.BUFFER_MAX):
    """Drive ``_QtLogHandler`` through the script and trace every step."""
    pane = _FakePane()
    handler = _QtLogHandler(pane)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler._buffer_max = buffer_max
    bar = pane.verticalScrollBar()
    trace = []
    for step in script:
        if step[0] == SCROLL:
            bar._value, bar._maximum = step[1], step[2]
            continue
        insert_mark = len(pane.inserts)
        scroll_mark = len(bar.set_calls)
        if step[0] == LOG:
            handler.emit(_record(step[1], step[2]))
        else:
            handler.set_paused(step[1])
        made = pane.inserts[insert_mark:]
        trace.append(
            {
                "insert_text": "".join(text for text, _r, _g, _b in made),
                "colors": [[r, g, b] for _t, r, g, b in made],
                "follows": len(bar.set_calls) - scroll_mark,
                "paused": handler._paused,
                "buffered": handler.buffered_count(),
                "dropped": handler._buffer_dropped,
            }
        )
    trace.append({"pane_text": pane.text})
    return trace


def run_new(script, buffer_max=surface.BUFFER_MAX):
    """Drive the view model through the same script and trace every step."""
    buffer = surface.ConsoleLogBuffer(buffer_max)
    pane_text = ""
    scroll_value = 0
    scroll_max = 0
    trace = []
    for step in script:
        if step[0] == SCROLL:
            scroll_value, scroll_max = step[1], step[2]
            continue
        pane_empty = pane_text == ""
        if step[0] == LOG:
            model = surface.build_view_model(
                buffer,
                [{"level": step[1], "text": step[2]}],
                pane_empty=pane_empty,
                scroll_value=scroll_value,
                scroll_max=scroll_max,
            )
        else:
            model = surface.build_view_model(
                buffer,
                [],
                paused=step[1],
                pane_empty=pane_empty,
                scroll_value=scroll_value,
                scroll_max=scroll_max,
            )
        lines = model["document"]["lines"]
        follows = 0
        for line in lines:
            one = surface.ConsoleDocument()
            one.append(
                surface.ConsoleLine(
                    line["text"],
                    line["level"],
                    line["color"],
                    line["r"],
                    line["g"],
                    line["b"],
                )
            )
            pane_text += one.insert_text(pane_text == "")
            if surface.follows_tail(scroll_value, scroll_max):
                scroll_value = scroll_max
                follows += 1
        trace.append(
            {
                "insert_text": model["document"]["insert_text"],
                "colors": [[ln["r"], ln["g"], ln["b"]] for ln in lines],
                "follows": follows,
                "paused": model["paused"],
                "buffered": model["buffered"],
                "dropped": model["dropped"],
            }
        )
    trace.append({"pane_text": pane_text})
    return trace


def digest(trace):
    return hashlib.sha256(json.dumps(trace, sort_keys=True).encode("utf-8")).hexdigest()


LEVELS_SCRIPT = [
    (LOG, "DEBUG", "debug line"),
    (LOG, "INFO", "info line"),
    (LOG, "WARNING", "warning line"),
    (LOG, "ERROR", "error line"),
    (LOG, "CRITICAL", "critical line"),
    (LOG, "TRACE", "level the map does not name"),
    (LOG, "", "empty level name"),
    (LOG, "ERROR", "INDICATOR PANEL rsi 55"),
    (LOG, "DEBUG", "before INDICATOR PANEL after"),
    (LOG, "INFO", "indicator panel lower case"),
    (LOG, "INFO", ""),
]

PAUSE_SCRIPT = [
    (LOG, "INFO", "before the pause"),
    (PAUSE, True),
    (LOG, "INFO", "held one"),
    (LOG, "WARNING", "held two"),
    (LOG, "ERROR", "INDICATOR PANEL held three"),
    (PAUSE, False),
    (LOG, "INFO", "after the resume"),
]

CAP_SCRIPT = [
    (LOG, "INFO", "painted first"),
    (PAUSE, True),
    (LOG, "INFO", "held one"),
    (LOG, "INFO", "held two"),
    (LOG, "INFO", "dropped one"),
    (LOG, "INFO", "dropped two"),
    (LOG, "INFO", "dropped three"),
    (PAUSE, False),
    (LOG, "INFO", "after the resume"),
]

TOGGLE_SCRIPT = [
    (PAUSE, False),
    (PAUSE, True),
    (PAUSE, True),
    (LOG, "INFO", "held while paused twice"),
    (PAUSE, 0),
    (PAUSE, 1),
    (LOG, "INFO", "held under a truthy int"),
    (PAUSE, ""),
    (LOG, "INFO", "painted again"),
]

SCROLL_SCRIPT = [
    (SCROLL, 0, 0),
    (LOG, "INFO", "bottom at zero"),
    (SCROLL, 100, 500),
    (LOG, "INFO", "scrolled well up"),
    (SCROLL, 480, 500),
    (LOG, "INFO", "exactly on the slack edge"),
    (SCROLL, 479, 500),
    (LOG, "INFO", "one below the slack edge"),
    (SCROLL, 481, 500),
    (LOG, "INFO", "one above the slack edge"),
]

DRAIN_SCROLL_SCRIPT = [
    (SCROLL, 200, 500),
    (PAUSE, True),
    (LOG, "INFO", "held one"),
    (LOG, "INFO", "held two"),
    (LOG, "INFO", "dropped one"),
    (SCROLL, 495, 500),
    (PAUSE, False),
]

ZERO_CAP_SCRIPT = [
    (LOG, "INFO", "painted first"),
    (PAUSE, True),
    (LOG, "INFO", "dropped one"),
    (LOG, "INFO", "dropped two"),
    (PAUSE, False),
    (LOG, "INFO", "after the resume"),
    (PAUSE, True),
    (LOG, "INFO", "dropped three"),
    (PAUSE, False),
]

SCRIPTS = {
    "levels": (LEVELS_SCRIPT, surface.BUFFER_MAX),
    "pause": (PAUSE_SCRIPT, surface.BUFFER_MAX),
    "cap": (CAP_SCRIPT, 2),
    "toggle": (TOGGLE_SCRIPT, surface.BUFFER_MAX),
    "scroll": (SCROLL_SCRIPT, surface.BUFFER_MAX),
    "drain_scroll": (DRAIN_SCROLL_SCRIPT, 2),
    "zero_cap": (ZERO_CAP_SCRIPT, 0),
}


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_old_and_new_traces_are_identical(name):
    """A step of the script paints something the other side does not."""
    script, buffer_max = SCRIPTS[name]
    old = run_old(script, buffer_max)
    new = run_new(script, buffer_max)
    assert new == old
    assert digest(new) == digest(old)


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_trace_is_not_empty(name):
    """The comparison passed by measuring nothing."""
    script, buffer_max = SCRIPTS[name]
    old = run_old(script, buffer_max)
    assert len(old) > 1
    assert any(step.get("insert_text") for step in old[:-1])
    assert old[-1]["pane_text"] != ""


def test_cap_script_reaches_the_drop_notice():
    """The cap script never filled the buffer, so no notice was compared."""
    notice = "[CONSOLE PAUSE] 3 messages dropped (buffer cap=2)"
    old = run_old(CAP_SCRIPT, 2)
    new = run_new(CAP_SCRIPT, 2)
    drained = [step for step in old[:-1] if notice in step["insert_text"]]
    assert len(drained) == 1
    assert drained[0]["dropped"] == 0
    assert max(step["dropped"] for step in old[:-1]) == 3
    assert notice in new[-1]["pane_text"]
    assert old[-1]["pane_text"] == new[-1]["pane_text"]


def test_resume_with_nothing_held_keeps_the_dropped_count():
    """A resume with an empty buffer painted a notice the handler withholds."""
    old = run_old(ZERO_CAP_SCRIPT, 0)
    new = run_new(ZERO_CAP_SCRIPT, 0)
    assert [step["dropped"] for step in old[:-1]] == [0, 0, 1, 2, 2, 2, 2, 3, 3]
    assert "CONSOLE PAUSE" not in old[-1]["pane_text"]
    assert new == old


def test_drop_notice_paints_the_warning_token():
    """The notice colour drifted from the literal the handler emits."""
    buffer = surface.ConsoleLogBuffer(1)
    buffer.set_paused(True)
    buffer.accept(surface.build_line("INFO", "held"))
    buffer.accept(surface.build_line("INFO", "dropped"))
    notice = buffer.set_paused(False)[-1]
    assert (notice.r, notice.g, notice.b) == (255, 170, 0)
    assert surface.rgb(ds.WARNING) == (255, 170, 0)


def test_the_drop_notice_level_and_the_drop_notice_token_name_one_colour():
    """The notice level and the notice token drifted apart."""
    assert surface.LEVEL_COLORS[surface.DROP_NOTICE_LEVEL] == surface.DROP_NOTICE_COLOR
    buffer = surface.ConsoleLogBuffer(1)
    buffer.set_paused(True)
    buffer.accept(surface.build_line("INFO", "held"))
    buffer.accept(surface.build_line("INFO", "dropped"))
    notice = buffer.set_paused(False)[-1]
    assert notice.level == surface.DROP_NOTICE_LEVEL
    assert notice.color == surface.DROP_NOTICE_COLOR


def test_rgb_matches_qcolor_on_every_token():
    """The Qt-free colour split disagrees with QColor on a token."""
    from PySide6.QtGui import QColor

    tokens = list(surface.LEVEL_COLORS.values()) + [
        surface.HIGHLIGHT_COLOR,
        surface.DROP_NOTICE_COLOR,
    ]
    for token in tokens:
        painted = QColor(token)
        assert surface.rgb(token) == (
            painted.red(),
            painted.green(),
            painted.blue(),
        )


def test_level_map_matches_the_handler_colors():
    """A level maps to a different token than the handler paints."""
    assert set(surface.LEVEL_COLORS) == set(_QtLogHandler.COLORS)
    for level, token in surface.LEVEL_COLORS.items():
        painted = _QtLogHandler.COLORS[level]
        assert surface.rgb(token) == (
            painted.red(),
            painted.green(),
            painted.blue(),
        )
    assert surface.rgb(surface.HIGHLIGHT_COLOR) == (
        _QtLogHandler.HIGHLIGHT.red(),
        _QtLogHandler.HIGHLIGHT.green(),
        _QtLogHandler.HIGHLIGHT.blue(),
    )


def test_buffer_cap_default_matches_the_handler():
    """The surface caps the pause buffer at a different depth."""
    handler = _QtLogHandler(_FakePane())
    assert surface.BUFFER_MAX == handler._buffer_max


def test_one_record_paints_the_pane_once():
    """``_QtLogRelay.append`` reaches the painter more than once per record."""
    pane = _FakePane()
    handler = _QtLogHandler(pane)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.emit(_record("INFO", "one line"))
    assert [text for text, _r, _g, _b in pane.inserts] == ["one line"]


def test_a_second_connection_paints_the_line_twice():
    """Positive control: the count above cannot see a doubled connection."""
    pane = _FakePane()
    handler = _QtLogHandler(pane)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler._relay.append.connect(handler._relay._deliver)
    handler.emit(_record("INFO", "one line"))
    assert len(pane.inserts) == 2


def test_bad_record_paints_nothing_on_both_sides():
    """A record that cannot be read raised instead of being skipped."""

    class _Raising:
        def get(self, _key, _default=None):
            raise ValueError("unreadable record")

    pane = _FakePane()
    handler = _QtLogHandler(pane)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.emit("not a record")
    assert pane.inserts == []

    model = surface.build_view_model(surface.ConsoleLogBuffer(), [_Raising()])
    assert model["document"]["lines"] == []
    assert model["document"]["insert_text"] == ""


def test_batch_insert_text_equals_the_line_by_line_inserts():
    """One batch and the same lines one at a time fill the pane differently."""
    records = [
        {"level": "INFO", "text": "one"},
        {"level": "ERROR", "text": "two"},
        {"level": "DEBUG", "text": "three"},
    ]
    batch = surface.build_view_model(
        surface.ConsoleLogBuffer(), records, pane_empty=False
    )
    pane_text = "already here"
    for record in records:
        one = surface.build_view_model(
            surface.ConsoleLogBuffer(),
            [record],
            pane_empty=(pane_text == ""),
        )
        pane_text += one["document"]["insert_text"]
    assert "already here" + batch["document"]["insert_text"] == pane_text


def test_view_model_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    model = surface.build_view_model(
        surface.ConsoleLogBuffer(),
        [{"level": "WARNING", "text": "INDICATOR PANEL live"}],
        scroll_value=10,
        scroll_max=10,
    )
    encoded = json.loads(json.dumps(model))
    assert encoded["document"]["insert_text"] == "INDICATOR PANEL live"
    assert encoded["highlight_color"] == list(surface.rgb(ds.PRIMARY))
    assert encoded["follow_tail"] is True
    assert encoded["buffer_max"] == surface.BUFFER_MAX


def test_bridge_registers_the_console_method():
    """The renderer cannot reach the Console surface through the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 7,
                "method": surface.METHOD,
                "params": {"records": [{"level": "ERROR", "text": "bridge line"}]},
            }
        ),
        registry,
    )
    assert answer["ok"] is True
    assert answer["result"]["document"]["lines"][0]["text"] == "bridge line"


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'console.log_lines', 'params':"
    " {'records': [{'level': 'CRITICAL', 'text': 'child line'}]}}),"
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
    """Reaching the Console surface pulled Qt into the backend process."""
    answered = _run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    assert answered["frame"]["result"]["document"]["lines"][0] == {
        "text": "child line",
        "level": "CRITICAL",
        "color": "#ff0044",
        "r": 255,
        "g": 0,
        "b": 68,
    }


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = _run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True
