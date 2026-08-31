"""The Qt screen recorder and the Qt-free surface, side by side.

A failure means the view model describes a different engine, a different
output file, a different program call, a different status line, a
different colour, a different screen or a different refusal than
``ScreenRecorder`` and ``RecorderToolbarWidget`` produce on the same
world.

No test here holds a capture device, opens an encoder, runs a program or
reads the wall clock. The clock, the stamp, the engines a machine has,
what a grab answered and what a program returned are all handed in: one
spec builds two independent worlds, and no object crosses between them.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time as clock_module
import datetime as datetime_module
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.main_tabs import screen_recorder_surface as surface
from tests.fixtures.host_fonts import (
    NARROW_LABEL,
    WIDE_LABEL,
    app_font_advance_px,
    has_real_fonts,
    skip_unless_no_fonts,
    skip_unless_real_fonts,
)
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_SOURCE = REPO_ROOT / "src" / "gui" / "screen_recorder.py"
WIRING_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "privacy_dot.py"
SIGNAL_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "launcher.py"
TIMER_BUILT_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "history_tab.py"
TIMER_SAME_NAME_FILE = REPO_ROOT / "src" / "gui" / "main_tabs" / "history_tab.py"
TIMER_UNBUILT_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "indicator_panel.py"
BUS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"
ELEMENT_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "dashboard_stat_card.py"
NESTED_CLASS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "stock_main_window.py"

PIXEL_SIZE = (220, 26)

WIRING_NEIGHBOUR_CONNECT_TOTAL = 1
SIGNAL_NEIGHBOUR_SIGNAL_TOTAL = 3
TIMER_NEIGHBOUR_BUILD_TOTAL = 1
TIMER_NEIGHBOUR_UNBUILT_TOTAL = 5
BUS_NEIGHBOUR_SUBSCRIBE_TOTAL = 2
BUS_NEIGHBOUR_EMIT_TOTAL = 5
ELEMENT_NEIGHBOUR_BUILD_TOTAL = 3

STAMP = "20260101_000000"
FROZEN_SECONDS = 1000.0
MISSING = object()


# ---------------------------------------------------------------------
# Reading a value the same way on both sides
# ---------------------------------------------------------------------


def as_text(value):
    """`value` with every number written as its own text.

    ``12`` and ``12.0`` are one value to a comparison and two different
    numbers to a reader, and two not-a-numbers are never equal to each
    other. Both are settled here before anything is compared.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, dict):
        return {key: as_text(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_text(inner) for inner in value]
    return value


def digest(value) -> str:
    """SHA-256 over every value in `value`, at every depth."""
    return hashlib.sha256(
        json.dumps(
            as_text(value), sort_keys=True, ensure_ascii=True, default=repr
        ).encode("utf-8")
    ).hexdigest()


def app():
    """The one application object every render is taken against."""
    from tests.qt_pixel import ensure_app

    return ensure_app()


def render_offscreen(widget, size):
    from tests.qt_pixel import render_widget

    return render_widget(widget, size)


def painted_colours(image) -> set:
    """Every colour name the render actually painted."""
    from PySide6.QtGui import QColor

    seen = set()
    for x in range(image.width()):
        for y in range(image.height()):
            seen.add(QColor(image.pixelColor(x, y)).name())
    return seen


def relative(paths, base) -> list:
    """`paths` written under `base`, with forward slashes."""
    root = str(base).replace("\\", "/").rstrip("/")
    written = []
    for path in paths:
        text = str(path).replace("\\", "/")
        written.append(text[len(root) :].lstrip("/") if text.startswith(root) else text)
    return written


# ---------------------------------------------------------------------
# The outward edges, stood in for. Nothing below reaches a real capture
# device, a real encoder, a real program, a real folder opener or the
# real clock.
# ---------------------------------------------------------------------


class Frame:
    """Stands in for the picture one grab returns.

    Composed, never a widget subclass: overriding a method the platform
    declares puts the name on the class for ever, and every later
    counter reads it there.
    """

    def __init__(self, width, height, write_error):
        self._width = width
        self._height = height
        self._write_error = write_error

    def isNull(self):
        return False

    def width(self):
        return self._width

    def height(self):
        return self._height

    def save(self, path, _image_format):
        if self._write_error is not None:
            raise self._write_error
        Path(path).write_bytes(b"1")
        return True

    def toImage(self):
        return FrameImage(self._width, self._height)


class FrameImage:
    """The bytes of one grabbed picture, as the encoders read them."""

    def __init__(self, width, height):
        self._width = width
        self._height = height

    def convertToFormat(self, _image_format):
        return self

    def width(self):
        return self._width

    def height(self):
        return self._height

    def bits(self):
        return b"\x00" * (self._width * self._height * 3)

    def bytesPerLine(self):
        return self._width * 3


class EmptyFrame:
    """What a grab returns when the capture device answered nothing."""

    def isNull(self):
        return True


class GrabSource:
    """The thing the shipped recorder grabs, answering a scripted list."""

    def __init__(self, answers, write_error):
        self.answers = list(answers)
        self.write_error = write_error
        self.calls = 0

    def grab(self):
        answer = (
            None
            if not self.answers
            else self.answers[min(self.calls, len(self.answers) - 1)]
        )
        self.calls += 1
        if isinstance(answer, BaseException):
            raise answer
        if answer is None:
            return EmptyFrame()
        return Frame(answer[0], answer[1], self.write_error)


class ProgramAnswer:
    """What one finished program handed back."""

    def __init__(self, returncode):
        self.returncode = returncode
        self.stderr = b"the encoder said no"


class ProgramRunner:
    """Stands in for every program the recorder starts. It starts none."""

    def __init__(self, has_ffmpeg, encode_returncode, concat_returncode):
        self.has_ffmpeg = has_ffmpeg
        self.encode_returncode = encode_returncode
        self.concat_returncode = concat_returncode
        self.commands = []

    def run(self, command, **named):
        asked = tuple(str(part) for part in command)
        if asked == surface.FFMPEG_VERSION_ARGS:
            return ProgramAnswer(0 if self.has_ffmpeg else 1)
        self.commands.append(asked)
        if "concat" in asked:
            return ProgramAnswer(self.concat_returncode)
        return ProgramAnswer(self.encode_returncode)

    def Popen(self, command, **named):
        self.commands.append(tuple(str(part) for part in command))


class FileMover:
    """Stands in for the moves and removals. It moves and removes none."""

    def __init__(self, move_error=None):
        self.move_error = move_error
        self.calls = []

    def move(self, source, target):
        self.calls.append(("move", str(source), str(target)))
        if self.move_error is not None:
            raise self.move_error

    def rmtree(self, target, **_named):
        self.calls.append(("rmtree", str(target)))


class InlineThreads:
    """Runs the recorder's background work on the calling thread.

    The shipped recorder starts an unowned daemon thread per chunk. Left
    real it outlives the test that started it and lands in another
    file's run.
    """

    class Thread:
        def __init__(self, target, args=(), name=None, daemon=None):
            self.target = target
            self.args = args
            self.name = name
            self.daemon = daemon

        def start(self):
            self.target(*self.args)


class HeldClock:
    """The clock, handed in. Every reading is the same second."""

    def time(self):
        return FROZEN_SECONDS


class HeldStamp:
    """The stamp, handed in. It reads no calendar."""

    def __init__(self, text):
        self.text = text

    def now(self):
        return self

    def strftime(self, _pattern):
        return self.text


class FolderOpener:
    """Stands in for the desktop's open-a-folder call. It opens none."""

    def __init__(self):
        self.opened = []

    def startfile(self, folder):
        self.opened.append(str(folder))


class VideoWriter:
    """Stands in for the direct video encoder. It encodes nothing."""

    def __init__(self, opens):
        self.opens = opens
        self.writes = 0
        self.released = False

    def isOpened(self):
        return self.opens

    def write(self, frame):
        self.writes += 1

    def release(self):
        self.released = True


def cv2_module(encoder_opens):
    """A stand-in for the OpenCV package, holding no encoder."""
    module = type(sys)("cv2")
    module.COLOR_RGB2BGR = 4
    module.VideoWriter_fourcc = lambda *_codes: 1
    module.writers = []

    def build_writer(*args, **named):
        writer = VideoWriter(encoder_opens)
        module.writers.append(writer)
        return writer

    module.VideoWriter = build_writer
    module.cvtColor = lambda frame, _code: frame
    return module


def numpy_module():
    """A stand-in for the array package. The CI fast lane installs none."""
    module = type(sys)("numpy")
    module.uint8 = "uint8"

    class Array:
        def reshape(self, *_shape):
            return self

    module.frombuffer = lambda _buffer, **_named: Array()
    return module


def pillow_module(save_error):
    """A stand-in for Pillow, writing one byte where it would write a GIF."""
    package = type(sys)("PIL")
    image_module = type(sys)("PIL.Image")

    class Picture:
        def __init__(self, size):
            self.size = size

        def resize(self, size, _resample=None):
            return Picture(size)

        def save(self, path, **named):
            if save_error is not None:
                raise save_error
            Path(path).write_bytes(b"1")

    image_module.LANCZOS = 1
    image_module.frombytes = lambda _mode, size, *_rest, **_named: Picture(size)
    package.Image = image_module
    return package


# ---------------------------------------------------------------------
# One spec, two independent worlds
# ---------------------------------------------------------------------


class Spec:
    """One description of a machine and a run, holding no object.

    Each side builds its own world from these numbers and words, so a
    grab, an error or a package never crosses from one side to the
    other.
    """

    def __init__(
        self,
        name,
        engine,
        grabs=((4, 4),),
        fps=1,
        ticks=0,
        encoder_opens=True,
        encode_returncode=0,
        concat_returncode=0,
        build_error=None,
        write_error=None,
        gif_save_error=None,
        move_error=None,
        stamp=STAMP,
        start_twice=False,
        stop_without_start=False,
    ):
        self.name = name
        self.engine = engine
        self.grabs = grabs
        self.fps = fps
        self.ticks = ticks
        self.encoder_opens = encoder_opens
        self.encode_returncode = encode_returncode
        self.concat_returncode = concat_returncode
        self.build_error = build_error
        self.write_error = write_error
        self.gif_save_error = gif_save_error
        self.move_error = move_error
        self.stamp = stamp
        self.start_twice = start_twice
        self.stop_without_start = stop_without_start


REFUSED = ("the capture device refused",)


def fresh(kind, text):
    """A new exception of `kind`, so no instance is shared by two sides."""
    return None if kind is None else kind(text)


def grabs_of(spec):
    """`spec`'s grab answers, as fresh objects for one side only."""
    return [
        RuntimeError(answer[0]) if answer == REFUSED else answer
        for answer in spec.grabs
    ]


CHUNK_AT_ONE_FPS = surface.chunk_frames(1)
LONG_STAMP = "s" * 200

SPECS = [
    Spec("png_happy", surface.PNG, ticks=3),
    Spec("png_no_device", surface.PNG, grabs=(None,)),
    Spec("png_device_refuses", surface.PNG, grabs=(REFUSED,)),
    Spec("png_device_refuses_mid_run", surface.PNG, grabs=((4, 4), REFUSED), ticks=3),
    Spec("png_device_empties_mid_run", surface.PNG, grabs=((4, 4), None), ticks=3),
    Spec("png_fps_zero", surface.PNG, fps=0),
    Spec("png_fps_negative", surface.PNG, fps=-1, ticks=4),
    Spec("png_fps_a_thousand_million", surface.PNG, fps=1000000000, ticks=2),
    Spec("png_fps_infinity", surface.PNG, fps=float("inf"), ticks=2),
    Spec("png_fps_minus_infinity", surface.PNG, fps=float("-inf"), ticks=2),
    Spec("png_fps_not_a_number", surface.PNG, fps=float("nan"), ticks=2),
    Spec("png_fps_is_text", surface.PNG, fps="30"),
    Spec("png_disk_full", surface.PNG, ticks=3, write_error=OSError),
    Spec("png_path_not_writable", surface.PNG, build_error=FileExistsError),
    Spec("png_stop_without_start", surface.PNG, stop_without_start=True),
    Spec("png_started_twice", surface.PNG, ticks=1, start_twice=True),
    Spec("cv2_happy", surface.CV2, ticks=3),
    Spec("cv2_encoder_refuses", surface.CV2, encoder_opens=False),
    Spec("cv2_no_device", surface.CV2, grabs=(None,)),
    Spec("cv2_stamp_is_empty", surface.CV2, stamp="", ticks=1),
    Spec("cv2_stamp_is_unicode", surface.CV2, stamp="ロケット", ticks=1),
    Spec("cv2_stamp_is_markup", surface.CV2, stamp="<b>&amp;</b>", ticks=1),
    Spec("cv2_stamp_has_an_apostrophe", surface.CV2, stamp="o'brien", ticks=1),
    Spec("cv2_stamp_has_a_newline", surface.CV2, stamp="one\ntwo", ticks=1),
    Spec("cv2_stamp_is_wrong_capitals", surface.CV2, stamp="AcV_SiM", ticks=1),
    Spec("cv2_stamp_is_a_number_as_text", surface.CV2, stamp="20260101", ticks=1),
    Spec("cv2_stamp_is_two_hundred_long", surface.CV2, stamp=LONG_STAMP, ticks=1),
    Spec("gif_happy", surface.GIF, ticks=6),
    Spec("gif_no_frames", surface.GIF, ticks=0),
    Spec("gif_over_the_cap", surface.GIF, ticks=(surface.MAX_GIF_FRAMES + 2) * 3),
    Spec("gif_save_refuses", surface.GIF, ticks=6, gif_save_error=OSError),
    Spec("gif_no_device", surface.GIF, grabs=(None,)),
    Spec("ffmpeg_happy", surface.FFMPEG, ticks=4),
    Spec("ffmpeg_encoder_refuses", surface.FFMPEG, ticks=4, encode_returncode=1),
    Spec("ffmpeg_two_chunks", surface.FFMPEG, ticks=CHUNK_AT_ONE_FPS * 2),
    Spec(
        "ffmpeg_join_refuses",
        surface.FFMPEG,
        ticks=CHUNK_AT_ONE_FPS * 2,
        concat_returncode=1,
    ),
    Spec("ffmpeg_move_refuses", surface.FFMPEG, ticks=4, move_error=OSError),
    Spec("ffmpeg_no_device", surface.FFMPEG, grabs=(None,)),
]

BY_NAME = {spec.name: spec for spec in SPECS}
SPEC_NAMES = [spec.name for spec in SPECS]

REFUSING_SPECS = [
    spec.name for spec in SPECS if spec.build_error is not None or spec.fps in (0, "30")
]


def engine_modules(spec):
    """The package answers a machine running `spec`'s engine gives."""
    if spec.engine == surface.CV2:
        return {
            "cv2": cv2_module(spec.encoder_opens),
            "numpy": numpy_module(),
            "PIL": None,
        }
    if spec.engine == surface.GIF:
        return {"cv2": None, "PIL": pillow_module(fresh(spec.gif_save_error, "gif"))}
    return {"cv2": None, "PIL": None}


class ModuleSwap:
    """Give one side its own package answers and put back what was there.

    The package table belongs to the whole process, so each side takes
    its turn under this and the table is restored before the next drive,
    a refusal included.
    """

    def __init__(self, answers):
        self.answers = answers
        self.held = {}

    def __enter__(self):
        for name, module in self.answers.items():
            self.held[name] = sys.modules.get(name, MISSING)
            sys.modules[name] = module
        image = self.answers.get("PIL")
        if image is not None:
            self.held["PIL.Image"] = sys.modules.get("PIL.Image", MISSING)
            sys.modules["PIL.Image"] = image.Image
        return self

    def __exit__(self, *_unused):
        for name, held in self.held.items():
            if held is MISSING:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = held
        return False


class ModuleAttributeSwap:
    """Give one module its own edges for one drive, then put them back."""

    def __init__(self, module, **edges):
        self.module = module
        self.edges = edges
        self.held = {}

    def __enter__(self):
        for name, value in self.edges.items():
            self.held[name] = getattr(self.module, name)
            setattr(self.module, name, value)
        return self

    def __exit__(self, *_unused):
        for name, held in self.held.items():
            setattr(self.module, name, held)
        return False


# ---------------------------------------------------------------------
# The shipped side
# ---------------------------------------------------------------------


def shipped_module():
    import src.gui.screen_recorder as shipped

    return shipped


def old_edges(spec):
    """The stand-ins one drive of the shipped side runs against."""
    return {
        "subprocess": ProgramRunner(
            spec.engine == surface.FFMPEG,
            spec.encode_returncode,
            spec.concat_returncode,
        ),
        "shutil": FileMover(fresh(spec.move_error, "move refused")),
        "threading": InlineThreads,
        "time": HeldClock(),
        "datetime": HeldStamp(spec.stamp),
        "os": FolderOpener(),
    }


def drive_old(spec):
    """Drive the shipped recorder and read the trace off it."""
    shipped = shipped_module()
    base = Path(tempfile.mkdtemp(prefix="acervator-recorder-old-"))
    out = base / "recordings"
    edges = old_edges(spec)
    with ModuleSwap(engine_modules(spec)), ModuleAttributeSwap(shipped, **edges):
        try:
            trace = _run_old(spec, shipped, base, out, edges)
        except Exception as exc:
            trace = {"refusal": type(exc).__name__}
    trace["base"] = base
    trace["edges"] = edges
    return trace


def _run_old(spec, shipped, base, out, edges):
    if spec.build_error is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"a file stands where the folder must go")
    source = GrabSource(grabs_of(spec), fresh(spec.write_error, "the disk is full"))
    recorder = shipped.ScreenRecorder(source, fps=spec.fps, output_dir=str(out))
    seen = []
    recorder.signals.status_changed.connect(
        lambda message, colour: seen.append((message, colour))
    )
    started = None
    stopped = None
    if spec.stop_without_start:
        stopped = recorder.stop()
    else:
        started = recorder.start()
        if spec.start_twice:
            recorder.start()
        for _ in range(spec.ticks):
            recorder._capture_frame()
        stopped = recorder.stop()
    writers = sys.modules["cv2"].writers if spec.engine == surface.CV2 else []
    return {
        "engine": recorder._engine,
        "started": started,
        "recording": recorder.is_recording,
        "output": relative([recorder.last_output], base)[0],
        "stopped_output": relative([stopped], base)[0],
        "grabs": source.calls,
        "statuses": [list(line) for line in seen],
        "commands": [
            relative(command, base) for command in edges["subprocess"].commands
        ],
        "moves": [relative(call, base) for call in edges["shutil"].calls],
        "files": sorted(
            relative((str(p) for p in base.rglob("*") if p.is_file()), base)
        ),
        "folders": sorted(
            relative((str(p) for p in base.rglob("*") if p.is_dir()), base)
        ),
        "stream_writes": sum(writer.writes for writer in writers),
    }


# ---------------------------------------------------------------------
# The surface side
# ---------------------------------------------------------------------

SURFACE_BASE = "/base"


def new_world(spec):
    """The world one drive of the surface runs against."""
    return surface.RecorderWorld(
        has_cv2=spec.engine == surface.CV2,
        has_ffmpeg=spec.engine == surface.FFMPEG,
        has_pillow=spec.engine == surface.GIF,
        grabs=grabs_of(spec),
        encoder_opens=spec.encoder_opens,
        encode_returncode=spec.encode_returncode,
        concat_returncode=spec.concat_returncode,
        write_error=fresh(spec.write_error, "the disk is full"),
        build_error=fresh(spec.build_error, "a file stands where the folder must go"),
        gif_save_error=fresh(spec.gif_save_error, "gif"),
        move_error=fresh(spec.move_error, "move refused"),
    )


def drive_new(spec):
    """Drive the surface and read the trace off it."""
    world = new_world(spec)
    try:
        trace = _run_new(spec, world)
    except Exception as exc:
        trace = {"refusal": type(exc).__name__}
    trace["base"] = SURFACE_BASE
    trace["world"] = world
    return trace


def _run_new(spec, world):
    out = f"{SURFACE_BASE}/recordings"
    capture = surface.Capture(world, fps=spec.fps, output_dir=out)
    started = None
    if spec.stop_without_start:
        stopped = capture.stop(0.0)
    else:
        started = capture.start(spec.stamp)
        if spec.start_twice:
            capture.start(spec.stamp)
        for _ in range(spec.ticks):
            capture.capture_frame(0)
        stopped = capture.stop(0.0)
    kept = [path for path in world.written_files if path not in world.deleted_files]
    return {
        "engine": capture.engine,
        "started": started,
        "recording": capture.is_recording,
        "output": relative([capture.last_output], SURFACE_BASE)[0],
        "stopped_output": relative([stopped], SURFACE_BASE)[0],
        "grabs": world.grab_calls,
        "statuses": [list(line) for line in capture.statuses],
        "commands": [relative(command, SURFACE_BASE) for command in world.commands],
        "moves": [relative(call, SURFACE_BASE) for call in capture.stopped_moves],
        "files": sorted(relative(kept, SURFACE_BASE)),
        "folders": sorted(
            set(name for name in relative(world.made_dirs, SURFACE_BASE) if name)
        ),
        "stream_writes": capture.stream_writes,
    }


BOOKKEEPING = ("base", "edges", "world")


def compared(trace) -> dict:
    """`trace` with the harness's own bookkeeping taken out."""
    return {key: value for key, value in trace.items() if key not in BOOKKEEPING}


# ---------------------------------------------------------------------
# Value for value, and by hash
# ---------------------------------------------------------------------


@pytest.mark.parametrize("name", SPEC_NAMES)
def test_the_two_sides_describe_the_same_run(name):
    """The surface describes a different run than the shipped recorder."""
    spec = BY_NAME[name]
    old = compared(drive_old(spec))
    new = compared(drive_new(spec))
    assert sorted(old) == sorted(new), (name, sorted(old), sorted(new))
    for key in sorted(old):
        assert as_text(old[key]) == as_text(new[key]), (name, key, old[key], new[key])
    assert digest(old) == digest(new), (name, old, new)


def test_every_spec_reaches_an_answer_or_a_refusal():
    """A spec was written into the table and never driven."""
    answered = 0
    refused = 0
    for spec in SPECS:
        trace = compared(drive_new(spec))
        if "refusal" in trace:
            refused += 1
        else:
            answered += 1
    assert answered + refused == len(SPECS)
    assert refused == len(REFUSING_SPECS), (refused, REFUSING_SPECS)
    assert answered > 0 and refused > 0


@pytest.mark.parametrize("name", REFUSING_SPECS)
def test_a_refused_run_names_the_same_type_on_both_sides(name):
    """The two sides refused with different classes of error."""
    old = compared(drive_old(BY_NAME[name]))
    new = compared(drive_new(BY_NAME[name]))
    assert "refusal" in old, (name, old)
    assert old["refusal"] == new["refusal"], (name, old, new)


def test_the_refusal_is_read_as_a_type_and_never_as_a_wording():
    """A refusal was compared by its message, which the platform writes."""
    for name in REFUSING_SPECS:
        old = compared(drive_old(BY_NAME[name]))
        assert set(old) == {"refusal"}, (name, old)
        assert old["refusal"] == old["refusal"].strip()
        assert " " not in old["refusal"], old["refusal"]


def test_the_hash_tells_two_different_answers_apart():
    """The hash reports one value for two different runs."""
    one = compared(drive_new(BY_NAME["png_happy"]))
    other = compared(drive_new(BY_NAME["gif_happy"]))
    assert one != other
    assert digest(one) != digest(other)


def test_the_hash_tells_a_whole_number_from_a_decimal():
    """A whole number and a decimal hash the same, so a swap passes."""
    assert digest({"fps": 12}) != digest({"fps": 12.0})
    assert as_text(12) != as_text(12.0)


def test_two_not_a_numbers_read_as_one_value_before_comparing():
    """Two not-a-numbers report a difference that is not one."""
    nan = float("nan")
    assert nan != nan
    assert as_text(nan) == as_text(float("nan"))
    assert digest({"fps": nan}) == digest({"fps": float("nan")})
    assert digest({"fps": nan}) != digest({"fps": float("inf")})


def test_a_swapped_order_is_reported_by_the_hash():
    """Two status lines swapped read as one trace."""
    lines = compared(drive_new(BY_NAME["gif_happy"]))["statuses"]
    assert len(lines) > 1
    swapped = list(lines)
    swapped[0], swapped[-1] = swapped[-1], swapped[0]
    assert digest(lines) != digest(swapped)


DIFFERENT_PAIR = ("png_happy", "ffmpeg_two_chunks")


def test_two_real_inputs_driven_one_through_each_side_are_told_apart():
    """The comparison passes whatever the second side produced."""
    first, second = DIFFERENT_PAIR
    old = compared(drive_old(BY_NAME[first]))
    new = compared(drive_new(BY_NAME[second]))
    assert digest(old) != digest(new), (old, new)


def test_the_same_two_real_inputs_the_other_way_round_are_told_apart():
    """The comparison reports in one direction only."""
    first, second = DIFFERENT_PAIR
    old = compared(drive_old(BY_NAME[second]))
    new = compared(drive_new(BY_NAME[first]))
    assert digest(old) != digest(new), (old, new)


def test_one_input_driven_through_both_sides_hashes_alike():
    """The comparison reports a difference where there is none."""
    for name in DIFFERENT_PAIR:
        assert digest(compared(drive_old(BY_NAME[name]))) == digest(
            compared(drive_new(BY_NAME[name]))
        ), name


@pytest.mark.parametrize("name", SPEC_NAMES)
def test_the_sample_hashes_are_reported(name):
    """The sample hash of one driven spec, for the record."""
    old = digest(compared(drive_old(BY_NAME[name])))
    new = digest(compared(drive_new(BY_NAME[name])))
    print(f"{name} old={old[:16]} new={new[:16]}")
    assert old == new


# ---------------------------------------------------------------------
# The frame rate the timer cannot hold
# ---------------------------------------------------------------------

TINY_FPS = 1e-9


def test_a_frame_rate_of_one_billionth_asks_a_delay_the_timer_refuses():
    """The recorder computes a delay and the platform timer takes it.

    The shipped recorder hands the delay to a timer holding a signed
    32-bit count of milliseconds. One billionth of a frame per second
    asks for more than that, so the run is left started with its folders
    made and no timer running. The surface reports the same delay and
    says it does not fit.
    """
    app()
    from PySide6.QtCore import QTimer

    delay = surface.capture_interval_ms(TINY_FPS)
    assert delay > surface.TIMER_MAX_MS
    assert surface.capture_interval_fits_timer(TINY_FPS) is False
    assert surface.capture_interval_fits_timer(surface.DEFAULT_FPS) is True
    timer = QTimer()
    timer.setInterval(surface.TIMER_MAX_MS)
    assert timer.interval() == surface.TIMER_MAX_MS
    with pytest.raises(OverflowError):
        timer.setInterval(surface.TIMER_MAX_MS + 1)


def test_the_shipped_recorder_is_left_started_by_the_delay_it_cannot_set():
    """A refused delay leaves no half-applied run behind."""
    spec = Spec("tiny_fps", surface.PNG, fps=TINY_FPS)
    old = drive_old(spec)
    assert compared(old) == {"refusal": "OverflowError"}
    assert sorted(
        relative((str(p) for p in old["base"].rglob("*") if p.is_dir()), old["base"])
    ) == ["recordings", f"recordings/{surface.frame_dir_name(STAMP)}"]


# ---------------------------------------------------------------------
# Step sequences, including ones that refuse part way
# ---------------------------------------------------------------------

STEP_SEQUENCES = {
    "record_then_stop": ("png_happy", ["start", "capture_frame", "stop"]),
    "flash_while_recording": (
        "png_happy",
        ["start", "flash", "capture_frame", "flash", "stop"],
    ),
    "stop_before_start": ("png_happy", ["stop", "start", "stop"]),
    "toggle_twice": ("png_happy", ["toggle", "capture_frame", "toggle"]),
    "start_refuses_no_device": ("png_no_device", ["start", "capture_frame", "stop"]),
    "start_refuses_no_folder": ("png_path_not_writable", ["start", "stop"]),
    "start_refuses_bad_rate": ("png_fps_is_text", ["start", "stop"]),
    "open_folder_then_record": ("png_happy", ["open_folder", "start", "stop"]),
}


def new_toolbar(spec, output_dir):
    """A toolbar view model pointed at its own world and a target."""
    toolbar = surface.ToolbarModel(new_world(spec), fps=spec.fps, output_dir=output_dir)
    toolbar.set_target(object())
    return toolbar


def old_toolbar_state(bar) -> dict:
    """What a reader sees on the shipped toolbar, read through Qt."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QLabel, QPushButton

    buttons = bar.findChildren(QPushButton)
    label = bar.findChild(QLabel)
    timers = bar.findChildren(QTimer)
    return {
        "status": label.text(),
        "status_style": label.styleSheet(),
        "record_label": buttons[0].text(),
        "record_style": buttons[0].styleSheet(),
        "flash_running": any(timer.isActive() for timer in timers),
    }


def run_old_steps(spec, bar, steps) -> list:
    """Drive `steps` on the shipped toolbar and report each one."""
    report = []
    for index, name in enumerate(steps):
        refusal = None
        try:
            if name == "start":
                bar._start_recording()
            elif name == "stop":
                bar._stop_recording()
            elif name == "toggle":
                bar._toggle_recording()
            elif name == "flash":
                bar._flash_rec()
            elif name == "capture_frame":
                if bar._recorder is not None:
                    bar._recorder._capture_frame()
            elif name == "open_folder":
                bar._open_folder()
            else:
                raise LookupError(name)
        except Exception as exc:
            refusal = type(exc).__name__
        report.append(
            dict(index=index, step=name, refusal=refusal, **old_toolbar_state(bar))
        )
        if refusal is not None:
            break
    return report


def run_new_steps(toolbar, steps) -> list:
    """Drive `steps` on the surface toolbar through its own helper."""
    named = [(step, STAMP) if step == "start" else step for step in steps]
    named = [("toggle", STAMP) if step == "toggle" else step for step in named]
    report = []
    for index, step in enumerate(named):
        name = step[0] if isinstance(step, tuple) else step
        refusal = None
        try:
            if name == "flash":
                toolbar.flash_record_button()
            else:
                inner = surface.run_steps(toolbar, [step])[0]
                refusal = inner["refusal"]
        except Exception as exc:
            refusal = type(exc).__name__
        report.append(
            dict(
                index=index,
                step=name,
                refusal=refusal,
                **surface.toolbar_state(toolbar),
            )
        )
        if refusal is not None:
            break
    return report


def drive_old_toolbar(spec, steps):
    shipped = shipped_module()
    base = Path(tempfile.mkdtemp(prefix="acervator-toolbar-old-"))
    out = base / "recordings"
    edges = old_edges(spec)
    with ModuleSwap(engine_modules(spec)), ModuleAttributeSwap(shipped, **edges):
        if spec.build_error is not None:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"a file stands where the folder must go")
        app()
        bar = shipped.RecorderToolbarWidget(
            target_widget=GrabSource(grabs_of(spec), None),
            fps=spec.fps,
            output_dir=str(out),
        )
        report = run_old_steps(spec, bar, steps)
    return report, base, edges, bar


@pytest.mark.parametrize("name", sorted(STEP_SEQUENCES))
def test_a_step_sequence_reads_the_same_on_both_sides(name):
    """A sequence of clicks leaves the two toolbars showing different things."""
    spec_name, steps = STEP_SEQUENCES[name]
    spec = BY_NAME[spec_name]
    old, base, edges, bar = drive_old_toolbar(spec, steps)
    new = run_new_steps(new_toolbar(spec, f"{SURFACE_BASE}/recordings"), steps)
    assert len(old) == len(new), (name, old, new)
    for old_step, new_step in zip(old, new):
        assert old_step["index"] == new_step["index"], (name, old_step, new_step)
        assert old_step["step"] == new_step["step"], (name, old_step, new_step)
        assert old_step["refusal"] == new_step["refusal"], (name, old_step, new_step)
        assert old_step == new_step, (name, old_step, new_step)


def test_a_sequence_that_refuses_part_way_reports_the_step_it_stopped_on():
    """A refused step ran the rest of the sequence anyway."""
    spec = BY_NAME["png_path_not_writable"]
    old, base, edges, bar = drive_old_toolbar(spec, ["start", "stop"])
    new = run_new_steps(
        new_toolbar(spec, f"{SURFACE_BASE}/recordings"), ["start", "stop"]
    )
    assert len(old) == 1, old
    assert old[0]["index"] == 0
    assert old[0]["step"] == "start"
    assert old[0]["refusal"] == "FileExistsError"
    assert old == new


def test_the_step_reader_reports_a_step_that_did_not_refuse():
    """The step reader marks a working step as refused."""
    spec = BY_NAME["png_happy"]
    old, base, edges, bar = drive_old_toolbar(spec, ["start"])
    assert old[0]["refusal"] is None, old
    assert old[0]["record_label"] == surface.STOP_LABEL


# ---------------------------------------------------------------------
# The enumeration
# ---------------------------------------------------------------------


def dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def parsed(path):
    return ast.parse(path.read_text(encoding="utf-8"))


def imported_names(tree) -> set:
    """Every name a module binds through an import."""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                found.add(alias.asname or alias.name.split(".")[0])
    return found


def widget_names(tree) -> set:
    """Every class name imported from a widget package."""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith(
            "QtWidgets"
        ):
            for alias in node.names:
                found.add(alias.asname or alias.name)
    return found


def connect_sites(path) -> list:
    """Every ``.connect(`` site in `path`, as signal and target."""
    found = []
    for node in ast.walk(parsed(path)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "connect"
        ):
            target = node.args[0]
            found.append(
                (
                    dotted(node.func.value),
                    (
                        "lambda"
                        if isinstance(target, ast.Lambda)
                        else dotted(
                            target.func if isinstance(target, ast.Call) else target
                        )
                    ),
                )
            )
    return sorted(found)


def timers_built(path) -> list:
    """Every timer `path` CONSTRUCTS. An import line alone is not one."""
    return [
        dotted(node.func)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call) and dotted(node.func).endswith("QTimer")
    ]


def timers_run_without_building(path) -> list:
    """Every timer `path` runs without holding one."""
    found = []
    for node in ast.walk(parsed(path)):
        if isinstance(node, ast.Call):
            name = dotted(node.func)
            if name.endswith("singleShot") or name.endswith("startTimer"):
                found.append(name)
    return sorted(found)


def bus_subscribes(path) -> list:
    """Every topic `path` listens on."""
    found = []
    for node in ast.walk(parsed(path)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "subscribe"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            found.append(node.args[0].value)
    return sorted(found)


def receiver_name(node) -> str:
    """The name the call was made on, a call of its own included."""
    if isinstance(node, ast.Call):
        return dotted(node.func)
    return dotted(node)


def bus_emits(path) -> list:
    """Every topic `path` puts on the bus.

    A Qt signal is emitted the same way, so the receiver must name a
    bus. ``get_event_bus().emit(...)`` is a call on a call, so the
    receiver is read through its own function name.
    """
    found = []
    for node in ast.walk(parsed(path)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "emit"
            and "bus" in receiver_name(node.func.value).lower()
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            found.append(node.args[0].value)
    return sorted(found)


def signals_declared(path) -> list:
    """Every signal `path` declares."""
    found = []
    for node in ast.walk(parsed(path)):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if dotted(node.value.func).endswith("Signal"):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        found.append(target.id)
    return sorted(found)


def signal_emits(path) -> list:
    """Every signal emission site in `path`, as the signal it names."""
    found = []
    for node in ast.walk(parsed(path)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "emit"
            and "bus" not in receiver_name(node.func.value).lower()
        ):
            found.append(dotted(node.func.value).rsplit(".", 1)[-1])
    return sorted(found)


def screen_elements(path) -> list:
    """Every widget `path` CONSTRUCTS, arrangers left out."""
    tree = parsed(path)
    names = widget_names(tree) | {
        name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and (node.level > 0 or (node.module or "").startswith("src."))
        for name in (alias.asname or alias.name for alias in node.names)
        if name[:1].isupper()
    }
    return sorted(
        made
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for made in [dotted(node.func)]
        if made in names and not made.endswith("Layout")
    )


def arrangers(path) -> list:
    """Every layout `path` constructs."""
    tree = parsed(path)
    names = widget_names(tree)
    return sorted(
        made
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for made in [dotted(node.func)]
        if made in names and made.endswith("Layout")
    )


def source_classes(path) -> list:
    """Every class the source declares, one inside a method included."""
    return sorted(
        node.name for node in ast.walk(parsed(path)) if isinstance(node, ast.ClassDef)
    )


def source_functions(path) -> list:
    """Every function the source declares, nested ones included."""
    return sorted(
        node.name
        for node in ast.walk(parsed(path))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def declared_members(holder) -> list:
    """Every method, property, static and class method `holder` declares.

    A signal is callable and is not a method. A property and a class
    method are not callable and are.
    """
    from PySide6.QtCore import Signal

    found = []
    for name, value in vars(holder).items():
        if name.startswith("__") and name != "__init__":
            continue
        if isinstance(value, Signal):
            continue
        if isinstance(value, (property, staticmethod, classmethod)) or callable(value):
            found.append(name)
    return sorted(found)


def narrow_members(holder) -> list:
    """Only what is callable. A property never is, so it is missed."""
    from PySide6.QtCore import Signal

    return sorted(
        name
        for name, value in vars(holder).items()
        if callable(value)
        and not name.startswith("__")
        and not isinstance(value, Signal)
    )


def loose_members(holder) -> list:
    """Every callable, a signal counted as a method."""
    return sorted(
        name
        for name, value in vars(holder).items()
        if callable(value) and not name.startswith("__")
    )


def test_the_recorder_wires_five_actions_and_the_surface_names_five():
    """The shipped recorder wires an action the surface names none of."""
    sites = connect_sites(SHIPPED_SOURCE)
    assert sites, "the counter found no wiring at all"
    assert len(surface.ACTIONS) == len(sites), (surface.ACTIONS, sites)
    assert [signal for signal, target in sites] == [
        "self._flash_timer.timeout",
        "self._open_btn.clicked",
        "self._rec_btn.clicked",
        "self._recorder.signals.status_changed",
        "self._timer.timeout",
    ], sites
    assert SHIPPED_SOURCE.read_text(encoding="utf-8").count(".connect(") == len(sites)
    neighbour = connect_sites(WIRING_NEIGHBOUR)
    assert len(neighbour) == WIRING_NEIGHBOUR_CONNECT_TOTAL, neighbour
    assert neighbour[0][0] == "self.clicked"


SHIPPED_SLOT_TO_SURFACE = {
    "_toggle_recording": "toggle_recording",
    "_open_folder": "open_output_folder",
    "_flash_rec": "flash_record_button",
    "_capture_frame": "capture_frame",
    "_set_status": "set_status",
}


def test_every_wired_slot_has_a_named_counterpart_on_the_surface():
    """A wired action reaches nothing on the surface."""
    shipped = shipped_module()
    slots = sorted(
        target.rsplit(".", 1)[-1] for _, target in connect_sites(SHIPPED_SOURCE)
    )
    assert slots == sorted(SHIPPED_SLOT_TO_SURFACE), slots
    assert sorted(surface.ACTIONS.values()) == sorted(SHIPPED_SLOT_TO_SURFACE.values())
    for slot, replacement in SHIPPED_SLOT_TO_SURFACE.items():
        holder = (
            shipped.ScreenRecorder
            if slot == "_capture_frame"
            else shipped.RecorderToolbarWidget
        )
        assert hasattr(holder, slot), slot
        assert hasattr(surface.Capture, replacement) or hasattr(
            surface.ToolbarModel, replacement
        ), replacement


def test_the_counterpart_table_reports_a_name_neither_side_holds():
    """The counterpart table accepts a name that is on neither side."""
    shipped = shipped_module()
    assert "_invented_slot" not in SHIPPED_SLOT_TO_SURFACE
    assert not hasattr(shipped.RecorderToolbarWidget, "_invented_slot")
    assert not hasattr(surface.ToolbarModel, "invented_action")


SHIPPED_CLASSES = ["RecorderToolbarWidget", "ScreenRecorder", "_RecorderSignals"]
SURFACE_CLASSES = {
    "Capture": "ScreenRecorder",
    "ToolbarModel": "RecorderToolbarWidget",
    "RecorderWorld": "the machine the recorder reads, handed in",
}


def test_every_shipped_class_method_and_function_has_a_counterpart():
    """The shipped recorder gained or lost a class, a method or a function."""
    shipped = shipped_module()
    live = sorted(
        name
        for name, value in vars(shipped).items()
        if isinstance(value, type) and value.__module__ == shipped.__name__
    )
    assert live == SHIPPED_CLASSES, live
    declared = source_classes(SHIPPED_SOURCE)
    assert declared.count("_RecorderSignals") == 2, declared
    assert sorted(set(declared)) == SHIPPED_CLASSES, declared
    functions = source_functions(SHIPPED_SOURCE)
    assert sorted(name for name in functions if name.startswith("_has")) == [
        "_has_cv2",
        "_has_ffmpeg",
        "_has_pillow",
    ]
    built = sorted(
        name
        for name, value in vars(surface).items()
        if isinstance(value, type) and value.__module__ == surface.__name__
    )
    assert built == sorted(SURFACE_CLASSES), built
    assert declared_members(shipped.ScreenRecorder), "the recorder declares no method"
    assert declared_members(shipped.RecorderToolbarWidget)


def test_a_signal_is_not_counted_as_a_method_and_a_property_is():
    """A signal reads as a method, and a property does not read at all.

    A signal is callable, so a loose counter takes it in. A property and
    a class method are not callable, so a narrow counter leaves them out.
    Both are proved on the neighbouring screens that really declare them.
    """
    from PySide6.QtCore import Signal

    from src.gui.indicator_panel import IndicatorVotingPanel
    from src.gui.launcher import ModeCard

    assert isinstance(vars(ModeCard)["clicked"], Signal)
    assert callable(vars(ModeCard)["clicked"])
    assert "clicked" in loose_members(ModeCard)
    assert "clicked" not in declared_members(ModeCard)
    assert "mousePressEvent" in declared_members(ModeCard)
    wide = declared_members(IndicatorVotingPanel)
    narrow = narrow_members(IndicatorVotingPanel)
    for name in ("_reading_fingerprint", "lock_timeframe", "selected_bot_id"):
        assert name in wide, name
    assert set(wide) - set(narrow) >= {"lock_timeframe", "selected_bot_id"}
    assert isinstance(vars(IndicatorVotingPanel)["lock_timeframe"], property)


def test_the_class_counter_finds_a_class_declared_inside_a_method():
    """A class declared inside a method is never counted."""
    from src.gui import stock_main_window

    declared = source_classes(NESTED_CLASS_NEIGHBOUR)
    assert "_StockLogHandler" in declared, declared
    live = sorted(
        name
        for name, value in vars(stock_main_window).items()
        if isinstance(value, type) and value.__module__ == stock_main_window.__name__
    )
    assert "_StockLogHandler" not in live, live
    assert set(declared) - set(live) == {"_StockLogHandler"}


def test_the_recorder_declares_two_signals_and_emits_one():
    """A signal was gained, lost, or emitted where the surface says none."""
    declared = signals_declared(SHIPPED_SOURCE)
    assert declared == sorted(surface.SIGNALS), (declared, surface.SIGNALS)
    emitted = sorted(set(signal_emits(SHIPPED_SOURCE)))
    assert emitted == sorted(surface.EMITTED_SIGNALS), emitted
    assert set(surface.SIGNALS) - set(surface.EMITTED_SIGNALS) == {"frame_captured"}
    neighbour = signals_declared(SIGNAL_NEIGHBOUR)
    assert len(neighbour) == SIGNAL_NEIGHBOUR_SIGNAL_TOTAL, neighbour


def test_the_recorder_builds_two_timers_and_runs_none_without_building():
    """A timer was gained or lost, in either of its two forms."""
    built = timers_built(SHIPPED_SOURCE)
    assert len(built) == len(surface.TIMERS), (built, surface.TIMERS)
    assert timers_run_without_building(SHIPPED_SOURCE) == []
    named = SHIPPED_SOURCE.read_text(encoding="utf-8").count("QTimer")
    assert named > len(built), (named, built)
    assert len(timers_built(TIMER_BUILT_NEIGHBOUR)) == TIMER_NEIGHBOUR_BUILD_TOTAL
    assert timers_built(TIMER_SAME_NAME_FILE) == []
    assert TIMER_BUILT_NEIGHBOUR != TIMER_SAME_NAME_FILE
    unbuilt = timers_run_without_building(TIMER_UNBUILT_NEIGHBOUR)
    assert len(unbuilt) == TIMER_NEIGHBOUR_UNBUILT_TOTAL, unbuilt


def test_the_recorder_touches_no_bus_in_either_direction():
    """The recorder listens or speaks on a bus the surface names none of."""
    assert bus_subscribes(SHIPPED_SOURCE) == []
    assert bus_emits(SHIPPED_SOURCE) == []
    assert surface.BUS_TOPICS == ()
    assert surface.BUS_EMITS == ()
    listened = bus_subscribes(BUS_NEIGHBOUR)
    spoken = bus_emits(BUS_NEIGHBOUR)
    assert len(listened) == BUS_NEIGHBOUR_SUBSCRIBE_TOTAL, listened
    assert len(spoken) == BUS_NEIGHBOUR_EMIT_TOTAL, spoken
    assert listened == ["wire.created", "wire.removed"]
    assert sorted(set(spoken)) == ["bot.log", "wire.created", "wire.removed"]


def test_the_recorder_builds_three_screen_elements_and_one_arranger():
    """A control was gained or lost from the toolbar."""
    built = screen_elements(SHIPPED_SOURCE)
    assert built == ["QLabel", "QPushButton", "QPushButton"], built
    assert len(built) == len(surface.SCREEN_ORDER)
    assert arrangers(SHIPPED_SOURCE) == ["QHBoxLayout"]
    named = SHIPPED_SOURCE.read_text(encoding="utf-8").count("QPushButton")
    assert named > built.count("QPushButton"), named
    neighbour = screen_elements(ELEMENT_NEIGHBOUR)
    assert len(neighbour) == ELEMENT_NEIGHBOUR_BUILD_TOTAL, neighbour
    assert neighbour == ["PrivacyDot", "QLabel", "QLabel"]


def test_the_neighbouring_controls_are_seven_different_files():
    """Two controls read one file, so one of the two was never measured."""
    named = [
        WIRING_NEIGHBOUR,
        SIGNAL_NEIGHBOUR,
        TIMER_BUILT_NEIGHBOUR,
        TIMER_UNBUILT_NEIGHBOUR,
        BUS_NEIGHBOUR,
        ELEMENT_NEIGHBOUR,
        NESTED_CLASS_NEIGHBOUR,
    ]
    assert len(set(named)) == len(named), named
    for path in named + [SHIPPED_SOURCE, TIMER_SAME_NAME_FILE]:
        assert path.is_file(), path


# ---------------------------------------------------------------------
# The completeness check
# ---------------------------------------------------------------------


def snapshot() -> dict:
    """Every value the surface exports, in one place."""
    world = surface.RecorderWorld(grabs=[(4, 4)], cwd="/here", platform="win32")
    toolbar = surface.ToolbarModel(world, fps=surface.DEFAULT_FPS, output_dir="/out")
    toolbar.set_target(object())
    screen = toolbar.build()
    started = surface.ToolbarModel(
        surface.RecorderWorld(grabs=[(4, 4)]), fps=1, output_dir="/out"
    )
    started.set_target(object())
    started.start_recording(STAMP)
    capture = started.capture
    capture.capture_frame(0)
    return {
        "screen": screen,
        "recording_screen": started.build(),
        "flash_lit": surface.flash_style(surface.flash_background(True)),
        "flash_dark": surface.flash_style(surface.flash_background(False)),
        "engines": list(surface.ENGINES),
        "engine_tips": {name: surface.engine_tip(name) for name in surface.ENGINES},
        "engine_colours": {
            name: surface.engine_colour(name) for name in surface.ENGINES
        },
        "fallback_tip": surface.engine_tip("no such engine"),
        "fallback_colour": surface.engine_colour("no such engine"),
        "actions": dict(surface.ACTIONS),
        "timers": dict(surface.TIMERS),
        "signals": list(surface.SIGNALS),
        "emitted_signals": list(surface.EMITTED_SIGNALS),
        "bus_topics": list(surface.BUS_TOPICS),
        "bus_emits": list(surface.BUS_EMITS),
        "step_names": list(surface.STEP_NAMES),
        "screen_order": list(surface.SCREEN_ORDER),
        "logger_names": list(surface.LOGGER_NAMES),
        "thread_name": surface.CAPTURE_THREAD_NAME,
        "open_commands": dict(surface.OPEN_COMMANDS),
        "open_request": list(surface.open_folder_request("", "win32", "/here")),
        "open_request_named": list(
            surface.open_folder_request("/out", "darwin", "/here")
        ),
        "open_request_other": list(
            surface.open_folder_request("/out", "plan9", "/here")
        ),
        "default_output_dir": surface.default_output_dir("/root"),
        "default_output_parts": list(surface.DEFAULT_OUTPUT_PARTS),
        "stamp_format": surface.STAMP_FORMAT,
        "output_names": {
            name: surface.output_name(name, STAMP) for name in surface.ENGINES
        },
        "frame_dir": surface.frame_dir_name(STAMP),
        "chunk_dir": surface.chunk_dir_name(STAMP),
        "frame_name": surface.frame_name(1),
        "chunk_name": surface.chunk_name(1),
        "frame_pattern": surface.FFMPEG_FRAME_PATTERN,
        "concat_list_name": surface.CONCAT_LIST_NAME,
        "concat_list_text": surface.concat_list_text(["/a.mp4", "/b.mp4"]),
        "encode_command": list(surface.encode_command("/f", "/c.mp4", 30, 0, 5)),
        "concat_command": list(surface.concat_command("/l.txt", "/o.mp4")),
        "version_args": list(surface.FFMPEG_VERSION_ARGS),
        "version_timeout_s": surface.FFMPEG_VERSION_TIMEOUT_S,
        "chunk_encode_timeout_s": surface.CHUNK_ENCODE_TIMEOUT_S,
        "concat_timeout_s": surface.CONCAT_TIMEOUT_S,
        "binary": surface.FFMPEG_BINARY,
        "codec": surface.VIDEO_CODEC,
        "pixel_format": surface.PIXEL_FORMAT,
        "movie_flags": surface.MOVIE_FLAGS,
        "fourcc": surface.FOURCC,
        "colour_conversion": surface.COLOUR_CONVERSION,
        "image_format": surface.IMAGE_FORMAT,
        "gif_resample": surface.GIF_RESAMPLE,
        "gif_resize_divisor": surface.GIF_RESIZE_DIVISOR,
        "gif_min_frame_ms": surface.GIF_MIN_FRAME_MS,
        "gif_frame_ms": surface.gif_frame_ms(surface.DEFAULT_FPS),
        "error_tail_chars": surface.ERROR_TAIL_CHARS,
        "chunk_seconds": surface.CHUNK_SECONDS,
        "gif_sample_rate": surface.GIF_SAMPLE_RATE,
        "max_gif_frames": surface.MAX_GIF_FRAMES,
        "default_fps": surface.DEFAULT_FPS,
        "flash_interval_ms": surface.FLASH_INTERVAL_MS,
        "timer_max_ms": surface.TIMER_MAX_MS,
        "capture_interval_ms": surface.capture_interval_ms(surface.DEFAULT_FPS),
        "capture_interval_fits": surface.capture_interval_fits_timer(
            surface.DEFAULT_FPS
        ),
        "chunk_frames": surface.chunk_frames(surface.DEFAULT_FPS),
        "colours": {
            "bg": surface.BG,
            "border": surface.BORDER,
            "grey": surface.GREY,
            "red": surface.RED,
            "green": surface.GREEN,
            "cyan": surface.CYAN,
            "gold": surface.GOLD,
            "flash_bg": surface.FLASH_BG,
            "recording_bg": surface.RECORDING_BG,
        },
        "labels": {
            "record": surface.REC_LABEL,
            "stop": surface.STOP_LABEL,
            "open": surface.OPEN_LABEL,
            "open_tip": surface.OPEN_TIP,
            "fallback_tip": surface.FALLBACK_TIP,
        },
        "font": {
            "family": surface.FONT_FAMILY,
            "button_px": surface.BUTTON_FONT_PX,
            "status_px": surface.STATUS_FONT_PX,
        },
        "sizes": {
            "button_height_px": surface.BUTTON_HEIGHT_PX,
            "open_width_px": surface.OPEN_BUTTON_WIDTH_PX,
            "open_height_px": surface.OPEN_BUTTON_HEIGHT_PX,
            "status_min_width_px": surface.STATUS_MIN_WIDTH_PX,
            "margins_px": list(surface.LAYOUT_MARGINS_PX),
            "spacing_px": surface.LAYOUT_SPACING_PX,
            "radius_px": surface.BUTTON_RADIUS_PX,
            "padding": surface.BUTTON_PADDING,
        },
        "statuses": {
            "start": surface.STATUS_START,
            "grab_failed": surface.STATUS_GRAB_FAILED,
            "encoder_failed": surface.STATUS_ENCODER_FAILED,
            "no_target": surface.STATUS_NO_TARGET,
            "no_frames": surface.STATUS_NO_FRAMES,
            "no_chunks": surface.STATUS_NO_CHUNKS,
            "final_chunk": surface.STATUS_FINAL_CHUNK,
        },
        "suffixes": {
            "video": surface.VIDEO_SUFFIX,
            "gif": surface.GIF_SUFFIX,
            "stem": surface.OUTPUT_STEM,
            "frame_dir_stem": surface.FRAME_DIR_STEM,
            "chunk_dir_stem": surface.CHUNK_DIR_STEM,
            "frame_name_format": surface.FRAME_NAME_FORMAT,
            "chunk_name_format": surface.CHUNK_NAME_FORMAT,
        },
        "toolbar_state": surface.toolbar_state(started),
        "method": surface.METHOD,
    }


def carried_values(value, seen=None) -> set:
    """Every value the snapshot carries, at every depth, as text."""
    seen = set() if seen is None else seen
    if isinstance(value, dict):
        for key, inner in value.items():
            seen.add(repr(key))
            carried_values(inner, seen)
    elif isinstance(value, (list, tuple)):
        for inner in value:
            carried_values(inner, seen)
    else:
        seen.add(repr(value))
    return seen


def surface_constants() -> dict:
    """Every value the surface module exports under a shouted name."""
    return {
        name: value
        for name, value in vars(surface).items()
        if name.isupper() and not name.startswith("_")
    }


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A surface value is compared by nothing, so a change to it passes."""
    carried = carried_values(snapshot())
    missing = []
    for name, value in surface_constants().items():
        if isinstance(value, dict):
            parts = list(value.keys()) + list(value.values())
        elif isinstance(value, (list, tuple)):
            parts = list(value)
        else:
            parts = [value]
        for part in parts:
            if repr(part) not in carried:
                missing.append((name, part))
    assert missing == [], missing


EMPTY_BY_DESIGN = {"bus_topics": surface.BUS_TOPICS, "bus_emits": surface.BUS_EMITS}


def test_every_snapshot_key_carries_a_value_the_surface_holds():
    """A snapshot key names something the surface does not have."""
    taken = snapshot()
    assert [key for key, value in taken.items() if value is None] == []
    empty = sorted(key for key, value in taken.items() if value in ("", [], {}))
    assert empty == sorted(EMPTY_BY_DESIGN), empty
    for key, held in EMPTY_BY_DESIGN.items():
        assert list(held) == list(taken[key]) == []
    assert len(taken) > len(surface.ACTIONS)


def test_the_completeness_check_can_report_a_missing_value():
    """The completeness check passes a value nothing reads."""
    carried = carried_values(snapshot())
    assert repr(surface.RED) in carried
    assert repr("a colour the surface never names") not in carried
    thinned = carried_values({"screen": snapshot()["screen"]})
    assert repr(surface.CHUNK_ENCODE_TIMEOUT_S) not in thinned
    assert len(thinned) < len(carried)


def test_both_the_completeness_checks_can_report():
    """Neither completeness check can fail, so both are decoration."""
    with pytest.raises(AssertionError):
        assert [("invented", 1)] == []
    assert carried_values({"a": {"b": [1, "two"]}}) == {"'a'", "'b'", "1", "'two'"}


# ---------------------------------------------------------------------
# The surface writes out its own values
# ---------------------------------------------------------------------

MOVED_VALUES = {
    "CHUNK_SECONDS": 31,
    "GIF_SAMPLE_RATE": 4,
    "MAX_GIF_FRAMES": 601,
}


def test_the_surface_does_not_follow_a_value_moved_in_the_shipped_file(monkeypatch):
    """The surface reads the shipped file, so a change moves both sides."""
    shipped = shipped_module()
    for name, moved in MOVED_VALUES.items():
        held = getattr(shipped, name)
        assert getattr(surface, name) == held, name
        monkeypatch.setattr(shipped, name, moved)
        assert getattr(surface, name) == held, name
        assert getattr(surface, name) != getattr(shipped, name), name
        monkeypatch.undo()


def test_the_comparison_names_exactly_which_value_moved(monkeypatch):
    """A moved value is reported without saying which one moved."""
    shipped = shipped_module()
    monkeypatch.setattr(shipped, "CHUNK_SECONDS", MOVED_VALUES["CHUNK_SECONDS"])
    moved = [
        name
        for name in MOVED_VALUES
        if getattr(shipped, name) != getattr(surface, name)
    ]
    assert moved == ["CHUNK_SECONDS"], moved
    monkeypatch.undo()
    assert [
        name
        for name in MOVED_VALUES
        if getattr(shipped, name) != getattr(surface, name)
    ] == []


def test_the_surface_does_not_follow_a_recorder_that_records_nothing(monkeypatch):
    """The surface leans on the shipped class rather than its own model."""
    shipped = shipped_module()

    class RecordsNothing:
        def __init__(self, *args, **named):
            pass

        def start(self, *args):
            return False

    monkeypatch.setattr(shipped, "ScreenRecorder", RecordsNothing)
    trace = compared(drive_new(BY_NAME["png_happy"]))
    assert trace["started"] is True
    assert trace["files"], trace


# ---------------------------------------------------------------------
# Shared state, and putting it back
# ---------------------------------------------------------------------


def test_each_side_gets_its_own_packages_and_the_table_is_put_back():
    """A drive leaves the package table holding one side's answers."""
    before = {name: sys.modules.get(name, MISSING) for name in ("cv2", "PIL", "numpy")}
    inside = {}
    with ModuleSwap(engine_modules(BY_NAME["cv2_happy"])):
        inside = {name: sys.modules.get(name, MISSING) for name in ("cv2", "numpy")}
    after = {name: sys.modules.get(name, MISSING) for name in ("cv2", "PIL", "numpy")}
    assert inside["cv2"] is not before["cv2"]
    assert inside["numpy"] is not before["numpy"]
    assert after == before, (before, after)


def test_the_package_table_is_put_back_after_a_refusal():
    """A refused drive leaves one side's packages in the table."""
    before = {name: sys.modules.get(name, MISSING) for name in ("cv2", "PIL")}
    drive_old(BY_NAME["png_fps_is_text"])
    assert {name: sys.modules.get(name, MISSING) for name in ("cv2", "PIL")} == before


def test_the_shipped_edges_are_put_back_after_a_refusal():
    """A refused drive leaves the shipped module holding a stand-in."""
    shipped = shipped_module()
    before = {
        name: getattr(shipped, name)
        for name in ("subprocess", "shutil", "threading", "time", "datetime", "os")
    }
    drive_old(BY_NAME["png_path_not_writable"])
    after = {name: getattr(shipped, name) for name in before}
    assert after == before, (before, after)
    assert after["subprocess"] is subprocess
    assert after["time"] is clock_module


def test_the_swap_is_watched_while_a_drive_is_running():
    """The swap never took, so the drive read the real edges."""
    shipped = shipped_module()
    real = shipped.subprocess
    with ModuleAttributeSwap(shipped, subprocess=ProgramRunner(True, 0, 0)):
        assert shipped.subprocess is not real
        assert isinstance(shipped.subprocess, ProgramRunner)
    assert shipped.subprocess is real


def test_the_shipped_recorder_writes_to_no_shared_table():
    """The recorder keeps state outside itself, so runs bleed together."""
    shipped = shipped_module()
    before = {
        name: value
        for name, value in vars(shipped).items()
        if name.isupper() and not name.startswith("_")
    }
    drive_old(BY_NAME["png_happy"])
    drive_old(BY_NAME["gif_happy"])
    after = {
        name: value
        for name, value in vars(shipped).items()
        if name.isupper() and not name.startswith("_")
    }
    assert after == before, (before, after)


def test_the_surface_writes_to_no_shared_table():
    """The surface keeps state outside itself, so runs bleed together."""
    before = dict(surface_constants())
    drive_new(BY_NAME["png_happy"])
    drive_new(BY_NAME["ffmpeg_two_chunks"])
    assert dict(surface_constants()) == before


def test_neither_side_edits_the_thing_it_was_handed():
    """A side changed the object it was given, so the caller's copy moved."""
    spec = BY_NAME["png_happy"]
    handed = grabs_of(spec)
    kept = list(handed)
    world = surface.RecorderWorld(grabs=handed)
    capture = surface.Capture(world, fps=1, output_dir="/out")
    capture.start(STAMP)
    capture.capture_frame(0)
    capture.stop(0.0)
    assert handed == kept, handed
    given_tips = dict(surface.ENGINE_TIPS)
    surface.build_view_model()["record_button"]["tooltip"]
    assert surface.ENGINE_TIPS == given_tips
    model = surface.view_model({})
    model["engines"].append("invented")
    assert list(surface.ENGINES) != model["engines"]


def test_the_shipped_recorder_does_not_edit_the_thing_it_grabs():
    """The recorder changed the widget it was handed."""
    spec = BY_NAME["png_happy"]
    old = drive_old(spec)
    assert "refusal" not in compared(old)
    assert old["edges"]["subprocess"].commands == []


# ---------------------------------------------------------------------
# The pictures
# ---------------------------------------------------------------------

PICTURE_STATES = ["idle", "recording", "flashed", "stopped"]


def toolbar_pair(state):
    """The shipped toolbar and the surface toolbar, driven the same way."""
    spec = BY_NAME["png_happy"]
    steps = {
        "idle": [],
        "recording": ["start"],
        "flashed": ["start", "flash"],
        "stopped": ["start", "capture_frame", "stop"],
    }[state]
    old, base, edges, bar = drive_old_toolbar(spec, steps)
    model = new_toolbar(spec, f"{SURFACE_BASE}/recordings")
    run_new_steps(model, steps)
    return bar, model


def model_payload(state):
    """The surface's screen after the same driving, stamped."""
    return sealed(toolbar_pair(state)[1].build())


def widget_painted_by_the_model(payload):
    """A toolbar built only from the payload, never from the shipped one."""
    payload = unaltered(payload)
    from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

    app()
    screen = QWidget()
    screen.setAccessibleName(payload["engine"])
    box = QHBoxLayout(screen)
    left, top, right, bottom = payload["layout"]["margins_px"]
    box.setContentsMargins(left, top, right, bottom)
    box.setSpacing(payload["layout"]["spacing_px"])
    for name in payload["layout"]["order"]:
        part = payload[name]
        if name == "status_label":
            label = QLabel(part["text"])
            label.setStyleSheet(part["style"])
            label.setFixedHeight(part["fixed_height_px"])
            label.setMinimumWidth(part["minimum_width_px"])
            box.addWidget(label)
            continue
        button = QPushButton(part["text"])
        if "fixed_width_px" in part:
            button.setFixedSize(part["fixed_width_px"], part["fixed_height_px"])
        else:
            button.setFixedHeight(part["fixed_height_px"])
        button.setStyleSheet(part["style"])
        button.setToolTip(part["tooltip"])
        box.addWidget(button)
    return screen


@pytest.mark.parametrize("state", PICTURE_STATES)
def test_the_two_sides_paint_one_picture(state):
    """The surface painted a different toolbar than the shipped one."""
    app()
    note = "%s, %s" % (state, "real fonts" if has_real_fonts() else "no fonts")
    bar, model = toolbar_pair(state)
    assert_pictures_match(
        old_side=render_offscreen(bar, PIXEL_SIZE),
        new_side=render_offscreen(
            widget_painted_by_the_model(sealed(model.build())), PIXEL_SIZE
        ),
        note=note,
    )


@pytest.mark.parametrize("state", PICTURE_STATES)
def test_the_painted_toolbar_shows_more_than_one_colour(state):
    """The two sides matched because the toolbar painted one flat colour."""
    app()
    bar, model = toolbar_pair(state)
    for side, image in (
        ("old", render_offscreen(bar, PIXEL_SIZE)),
        (
            "new",
            render_offscreen(
                widget_painted_by_the_model(sealed(model.build())), PIXEL_SIZE
            ),
        ),
    ):
        seen = painted_colours(image)
        print(f"{state} {side} colours={len(seen)}")
        assert len(seen) > 1, f"{state} {side} painted one colour"


def test_the_picture_comparison_can_report_a_difference():
    """The picture check passes whatever the second side paints.

    Two real states, one taken off each side. The record button reads
    five characters in one and six in the other, and its background is a
    different colour, so the two differ whatever fonts the host holds.
    """
    app()
    idle_bar, _ = toolbar_pair("idle")
    _, recording_model = toolbar_pair("recording")
    assert surface.REC_LABEL != surface.STOP_LABEL
    assert_pictures_differ(
        old_side=render_offscreen(idle_bar, PIXEL_SIZE),
        new_side=render_offscreen(
            widget_painted_by_the_model(sealed(recording_model.build())), PIXEL_SIZE
        ),
        note="an idle toolbar against a recording one",
    )


UNSET_RULE = "QWidget { background: #ff00ff; }"


def test_a_rule_neither_side_sets_moves_the_picture():
    """The render ignores the skin, so a lost style sheet would not show.

    Every reading here is taken off a render. The rule is put back and
    the third render is compared with the first, so restoring is proved
    by a picture and never by asking a live object what it holds.
    """
    app()
    from PySide6.QtWidgets import QApplication

    assert UNSET_RULE not in surface.button_style(
        surface.BG, surface.RED, surface.RED, surface.CYAN
    )
    assert UNSET_RULE not in surface.status_style(surface.GREY)
    bar, _ = toolbar_pair("idle")
    plain = render_offscreen(bar, PIXEL_SIZE)
    held = QApplication.instance().styleSheet()
    try:
        QApplication.instance().setStyleSheet(UNSET_RULE)
        skinned = render_offscreen(bar, PIXEL_SIZE)
    finally:
        QApplication.instance().setStyleSheet(held)
    put_back = render_offscreen(bar, PIXEL_SIZE)
    assert_pictures_differ(
        old_side=plain, new_side=skinned, note="a rule neither side sets"
    )
    assert_pictures_match(
        old_side=plain, new_side=put_back, note="the rule was put back"
    )


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, which measures the host's fonts."""
    app()
    payload = model_payload("idle")
    payload["record_button"]["text"] = "MOVED"
    with pytest.raises(AssertionError) as reported:
        widget_painted_by_the_model(payload)
    assert "altered after it came off" in str(reported.value)
    with pytest.raises(AssertionError):
        widget_painted_by_the_model(surface.build_view_model())


def test_the_host_font_question_is_asked_and_not_assumed():
    """The suite pinned the machine it was written on."""
    app()
    assert len(NARROW_LABEL) == len(WIDE_LABEL)
    narrow = app_font_advance_px(NARROW_LABEL)
    wide = app_font_advance_px(WIDE_LABEL)
    if has_real_fonts():
        assert narrow != wide, "the host reports fonts and every glyph has one width"
    else:
        assert narrow == wide, "the host reports no fonts and the glyphs differ"


@skip_unless_no_fonts
def test_two_equal_length_status_lines_measure_alike_without_fonts():
    """Every family is a box font, and two equal-length lines still differ."""
    app()
    assert len(surface.STATUS_NO_FRAMES) == len(surface.STATUS_NO_TARGET)
    assert app_font_advance_px(surface.STATUS_NO_FRAMES) == app_font_advance_px(
        surface.STATUS_NO_TARGET
    )


@skip_unless_real_fonts
def test_the_two_marker_strings_measure_apart_with_fonts():
    """The glyphs decide their own width, and the marker pair measures alike."""
    app()
    assert app_font_advance_px(NARROW_LABEL) != app_font_advance_px(WIDE_LABEL)


# ---------------------------------------------------------------------
# What a picture cannot see, read off both sides instead
# ---------------------------------------------------------------------


def test_the_tooltips_are_read_off_both_sides():
    """A tip a picture never paints went missing."""
    from PySide6.QtWidgets import QPushButton

    bar, model = toolbar_pair("idle")
    buttons = bar.findChildren(QPushButton)
    screen = model.build()
    assert buttons[0].toolTip() == screen["record_button"]["tooltip"]
    assert buttons[1].toolTip() == screen["open_button"]["tooltip"]
    assert buttons[0].toolTip() == surface.ENGINE_TIPS[surface.PNG]


def test_the_layout_boxes_are_read_off_both_sides():
    """A margin or a spacing a picture cannot show moved."""
    bar, model = toolbar_pair("idle")
    box = bar.layout()
    margins = box.contentsMargins()
    screen = model.build()
    assert [
        margins.left(),
        margins.top(),
        margins.right(),
        margins.bottom(),
    ] == screen["layout"]["margins_px"]
    assert box.spacing() == screen["layout"]["spacing_px"]
    assert box.count() == len(screen["layout"]["order"])


def test_the_flash_delay_is_read_off_both_sides():
    """The flash runs at a different rate on the two sides."""
    from PySide6.QtCore import QTimer

    bar, model = toolbar_pair("idle")
    timers = bar.findChildren(QTimer)
    assert len(timers) == 1, timers
    assert timers[0].interval() == model.build()["flash_interval_ms"]


def test_the_open_button_asks_for_the_same_folder_on_both_sides():
    """The open button opens a different folder than the surface names."""
    spec = BY_NAME["png_happy"]
    old, base, edges, bar = drive_old_toolbar(spec, ["open_folder"])
    opened = edges["os"].opened + [part for part in edges["subprocess"].commands]
    assert opened, "the open button asked for nothing"
    asked = str(opened[0]) if isinstance(opened[0], str) else str(opened[0][-1])
    model = new_toolbar(spec, str(base / "recordings"))
    model.world.platform = sys.platform
    command, folder = model.open_output_folder()
    assert Path(asked) == Path(folder).resolve(), (asked, folder)
    assert command == surface.OPEN_COMMANDS.get(sys.platform, "xdg-open")


def test_the_open_button_falls_back_to_the_working_folder_when_none_is_set():
    """An unset output folder opens the recordings folder, not the run's own."""
    command, folder = surface.open_folder_request("", "win32", "/somewhere")
    assert folder == "/somewhere"
    assert surface.default_output_dir("/somewhere") != folder
    assert command == surface.OPEN_COMMANDS["win32"]


# ---------------------------------------------------------------------
# The bridge, and the surface reached without Qt
# ---------------------------------------------------------------------


def bridge_answer(params, request_id=1):
    from src.core.desktop_bridge import build_registry, handle_line

    line = json.dumps({"id": request_id, "method": surface.METHOD, "params": params})
    return handle_line(line, build_registry())


def test_the_bridge_registers_the_screen_recorder_method():
    """The frontend cannot reach the recorder screen."""
    from src.core.desktop_bridge import build_registry

    registry = build_registry()
    assert surface.METHOD in registry
    assert registry[surface.METHOD] is surface.view_model
    assert "screen_recorder.no_such_method" not in registry


def test_the_bridge_answers_with_the_screen_the_surface_builds():
    """The bridge answers with something other than the view model."""
    answer = bridge_answer({"has_pillow": True, "fps": 12})
    assert answer["ok"] is True
    assert answer["id"] == 1
    assert answer["result"]["screen"]["engine"] == surface.GIF
    assert answer["result"]["screen"][
        "capture_interval_ms"
    ] == surface.capture_interval_ms(12)
    assert answer["result"]["engines"] == list(surface.ENGINES)


def test_the_bridge_answer_is_json_serialisable():
    """The answer holds something the pipe cannot carry."""
    answer = bridge_answer({"has_cv2": True})
    text = json.dumps(answer, ensure_ascii=True)
    assert json.loads(text) == answer
    assert "\n" not in text


def test_the_bridge_reports_a_request_it_cannot_use():
    """A bad request reads as a working answer."""
    answer = bridge_answer({"fps": "not a number"})
    assert answer["ok"] is False
    assert answer["error"]["type"] == "ValueError"


PROBE = """
import json, sys
sys.path.insert(0, %(repo)r)
import socket
reached = []


def _count(*a, **k):
    reached.append(a)
    return None


socket.socket.connect = _count
socket.socket.connect_ex = _count
socket.create_connection = _count
socket.getaddrinfo = _count
%(prelude)s
from src.core.desktop_bridge import build_registry, handle_line
answer = handle_line(
    json.dumps({"id": 7, "method": "screen_recorder.state", "params": {}}),
    build_registry(),
)
print(json.dumps({
    "qt": sorted(
        n for n in sys.modules
        if n.startswith("PySide6") and sys.modules[n] is not None
    )[:1],
    "ok": answer["ok"],
    "engine": answer["result"]["screen"]["engine"] if answer["ok"] else None,
    "reached": len(reached),
}))
"""


def run_probe(prelude):
    """Run one probe in a fresh process and return what it printed.

    The probe is handed in on the child's stdin, so the command this
    starts is two written-down words and carries no input of its own.
    """
    finished = subprocess.run(
        [sys.executable, "-"],
        input=(PROBE % {"repo": str(REPO_ROOT), "prelude": prelude}).encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=90,
        check=False,
    )
    assert finished.returncode == 0, finished.stderr.decode()
    return json.loads(finished.stdout.decode().strip().splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """The surface pulls Qt in, so the frontend cannot run without it."""
    answered = run_probe("sys.modules['PySide6'] = None")
    assert answered["qt"] == [], answered
    assert answered["ok"] is True
    assert answered["engine"] in surface.ENGINES


def test_the_qt_probe_can_report_qt():
    """The probe reports no Qt whatever the process loaded."""
    answered = run_probe("import PySide6")
    assert answered["qt"] == ["PySide6"], answered


def test_the_probe_counts_a_connection_the_child_tried_to_open():
    """The connection counter never reaches the child process."""
    clean = run_probe("")
    assert clean["reached"] == 0, clean
    dirty = run_probe("socket.getaddrinfo('localhost', 9)")
    assert dirty["reached"] == 1, dirty


def test_this_run_opens_no_connection_of_its_own(monkeypatch):
    """A drive reached the network."""
    reached = []

    def refuse(*args, **named):
        reached.append(args)
        raise AssertionError("this run tried to reach the network")

    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    for name in ("png_happy", "ffmpeg_two_chunks", "gif_happy", "cv2_happy"):
        assert digest(compared(drive_old(BY_NAME[name]))) == digest(
            compared(drive_new(BY_NAME[name]))
        )
    assert reached == [], reached
    with pytest.raises(AssertionError):
        refuse("a seeded call")
    assert len(reached) == 1


# ---------------------------------------------------------------------
# The throwaway home
# ---------------------------------------------------------------------

HOME_PROBE = """
import json, os, sys
from pathlib import Path
sys.path.insert(0, %(repo)r)
home = Path(os.environ["ACERVATOR_TEST_HOME"])
before = sorted(str(p) for p in home.rglob("*") if p.is_file())
from src.gui.main_tabs import screen_recorder_surface as surface
made = []
for cv2, ffmpeg, pillow in ((1,0,0), (0,1,0), (0,0,1), (0,0,0)):
    world = surface.RecorderWorld(
        has_cv2=bool(cv2), has_ffmpeg=bool(ffmpeg), has_pillow=bool(pillow),
        grabs=[(4, 4)],
    )
    bar = surface.ToolbarModel(world, fps=1, output_dir=str(home / "recordings"))
    bar.set_target(object())
    surface.run_steps(bar, [("start", "20260101_000000"), "capture_frame", ("stop", 0.0)])
    made.append(bar.build()["engine"])
%(extra)s
after = sorted(str(p) for p in home.rglob("*") if p.is_file())
print(json.dumps({"before": len(before), "after": len(after), "engines": made}))
"""


def run_home_probe(extra):
    """Drive the surface in a fresh process under a throwaway home."""
    home = Path(tempfile.mkdtemp(prefix="acervator-throwaway-home-"))
    environment = dict(os.environ)
    environment["ACERVATOR_TEST_HOME"] = str(home)
    finished = subprocess.run(
        [sys.executable, "-"],
        input=(HOME_PROBE % {"repo": str(REPO_ROOT), "extra": extra}).encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        env=environment,
        timeout=90,
        check=False,
    )
    assert finished.returncode == 0, finished.stderr.decode()
    return json.loads(finished.stdout.decode().strip().splitlines()[-1]), home


def test_a_whole_run_of_every_engine_creates_no_file():
    """The surface wrote a file, so a view model reached the disk."""
    answered, home = run_home_probe("")
    assert answered["before"] == 0
    assert answered["after"] == 0, answered
    assert sorted(answered["engines"]) == sorted(surface.ENGINES)
    assert list(home.rglob("*")) == []


def test_the_file_counter_reports_a_file_that_was_created():
    """The file counter cannot see a file, so its zero means nothing."""
    answered, home = run_home_probe('(home / "one.txt").write_bytes(b"1")')
    assert answered["before"] == 0
    assert answered["after"] == 1, answered
    assert [p.name for p in home.rglob("*")] == ["one.txt"]


# ---------------------------------------------------------------------
# The clock, held still
# ---------------------------------------------------------------------


class RefusingClock:
    """A clock that refuses every reading."""

    def __init__(self):
        self.asked = 0

    def __call__(self, *args, **named):
        self.asked += 1
        raise AssertionError("this run read the wall clock")

    def now(self, *args, **named):
        return self(*args, **named)


def test_neither_the_surface_nor_this_test_reads_the_wall_clock(monkeypatch):
    """A run read the clock, so its answer moves with the day."""
    trap = RefusingClock()
    monkeypatch.setattr(clock_module, "time", trap)
    monkeypatch.setattr(clock_module, "monotonic", trap)
    monkeypatch.setattr(clock_module, "perf_counter", trap)
    monkeypatch.setattr(datetime_module, "datetime", trap)
    for name in SPEC_NAMES:
        drive_new(BY_NAME[name])
    snapshot()
    surface.view_model({})
    assert trap.asked == 0, trap.asked
    with pytest.raises(AssertionError):
        clock_module.time()
    assert trap.asked == 1


def test_the_shipped_recorder_is_handed_its_clock_and_its_stamp():
    """The shipped recorder read the real clock during a drive."""
    shipped = shipped_module()
    assert shipped.time is clock_module
    assert shipped.datetime is datetime_module.datetime
    old = compared(drive_old(BY_NAME["png_happy"]))
    assert surface.frame_dir_name(STAMP) in old["output"], old
    again = compared(drive_old(BY_NAME["png_happy"]))
    assert digest(old) == digest(again)


def test_the_stamp_the_recorder_is_handed_reaches_the_file_name():
    """The handed-in stamp is dropped and the calendar is read instead."""
    spec = BY_NAME["cv2_stamp_is_wrong_capitals"]
    old = compared(drive_old(spec))
    new = compared(drive_new(spec))
    assert spec.stamp in old["output"], old
    assert old["output"] == new["output"]
    assert surface.output_name(surface.CV2, spec.stamp).startswith(surface.OUTPUT_STEM)
