"""screen_recorder_surface.py -- the recorder toolbar and one capture run
as a view model, without Qt.

The screen recorder writes a video of a widget. It picks the best of the
four engines the machine offers, names the files it will write, runs a
timer that grabs one frame per tick, and paints a small toolbar of two
buttons and a status label.

Nothing here holds a device, opens an encoder, runs a program or writes
a file. Every outward fact the recorder reads -- which engines the
machine has, what a grab returned, whether the encoder opened, what a
program answered, the time, the working folder -- is handed in on
``RecorderWorld``. The module names the devices, the codecs and the file
paths as text, and a caller that wants any of them to happen does that
itself.

``ToolbarModel.build`` returns the screen: the two buttons, their
labels, their colours, their style sheets, the status label and the
layout boxes. ``Capture`` is one recording run: ``start`` picks the
engine and names the output, ``capture_frame`` advances one tick, and
``stop`` closes it. ``run_steps`` drives a named sequence and reports
each step's index, name, refusal type and status, so a sequence that
refuses part way is read step by step.

A refusal is a type. A world that cannot build a run raises the class
the world carries; a world the recorder answers with a message returns
False and shows that message.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``screen_recorder.state`` method, which is how the Electron renderer
reaches it. Every value below is written out here rather than read from
``src.gui.screen_recorder``, so a value changed on one side alone is
reported. Nothing here imports Qt, and nothing runs at import time that
reads a machine, a clock or a disk.
"""

from __future__ import annotations

from typing import Any

METHOD = "screen_recorder.state"

CHUNK_SECONDS = 30
GIF_SAMPLE_RATE = 3
MAX_GIF_FRAMES = 600
DEFAULT_FPS = 30
FLASH_INTERVAL_MS = 600
TIMER_MAX_MS = 2**31 - 1

CV2 = "cv2"
FFMPEG = "ffmpeg"
GIF = "gif"
PNG = "png"
ENGINES = (CV2, FFMPEG, GIF, PNG)

BG = "#070710"
BORDER = "#1a1a3f"
GREY = "#667799"
RED = "#ff3366"
GREEN = "#00ff88"
CYAN = "#00FFEE"
GOLD = "#ffaa00"
FLASH_BG = "#2a0008"
RECORDING_BG = "#1a0008"

ENGINE_COLOURS = {CV2: GREEN, FFMPEG: GOLD, GIF: CYAN, PNG: GREY}

ENGINE_TIPS = {
    CV2: "Record → MP4 (OpenCV — direct stream, no temp files)",
    FFMPEG: "Record → MP4 (ffmpeg — 30s rolling chunks, auto-purge)",
    GIF: "Record → GIF (Pillow — sampled at 10fps, held in memory)",
    PNG: "Record → PNG rolling window (last 30s kept on disk)",
}

FALLBACK_TIP = "Record"
OPEN_TIP = "Open recordings folder"

REC_LABEL = "● REC"
STOP_LABEL = "■ STOP"
OPEN_LABEL = "\U0001f4c1"

FONT_FAMILY = "Consolas"
BUTTON_FONT_PX = 8
STATUS_FONT_PX = 7
BUTTON_HEIGHT_PX = 20
OPEN_BUTTON_WIDTH_PX = 22
OPEN_BUTTON_HEIGHT_PX = 20
STATUS_MIN_WIDTH_PX = 55
LAYOUT_MARGINS_PX = (2, 0, 2, 0)
LAYOUT_SPACING_PX = 3
BUTTON_RADIUS_PX = 3
BUTTON_PADDING = "1px 6px"

STAMP_FORMAT = "%Y%m%d_%H%M%S"
OUTPUT_STEM = "ACV_Sim_"
VIDEO_SUFFIX = ".mp4"
GIF_SUFFIX = ".gif"
FRAME_DIR_STEM = "_frames_"
CHUNK_DIR_STEM = "_chunks_"
FRAME_NAME_FORMAT = "frame_{index:06d}.png"
FFMPEG_FRAME_PATTERN = "frame_%06d.png"
CHUNK_NAME_FORMAT = "chunk_{index:04d}.mp4"
CONCAT_LIST_NAME = "concat.txt"
DEFAULT_OUTPUT_PARTS = ("logs", "simulator", "recordings")

FFMPEG_BINARY = "ffmpeg"
FFMPEG_VERSION_ARGS = ("ffmpeg", "-version")
FFMPEG_VERSION_TIMEOUT_S = 3
CHUNK_ENCODE_TIMEOUT_S = 120
CONCAT_TIMEOUT_S = 300
VIDEO_CODEC = "libx264"
PIXEL_FORMAT = "yuv420p"
MOVIE_FLAGS = "+faststart"
FOURCC = "mp4v"
COLOUR_CONVERSION = "COLOR_RGB2BGR"
IMAGE_FORMAT = "Format_RGB888"
GIF_RESAMPLE = "LANCZOS"
GIF_MIN_FRAME_MS = 50
GIF_RESIZE_DIVISOR = 2
ERROR_TAIL_CHARS = 300

OPEN_COMMANDS = {
    "win32": "os.startfile",
    "darwin": "open",
    "linux": "xdg-open",
}

CAPTURE_THREAD_NAME = "screen-recorder"
LOGGER_NAMES = ("acervator.gui.recorder", "acervator.recorder")

STATUS_START = "● REC  0s"
STATUS_GRAB_FAILED = "Grab failed"
STATUS_ENCODER_FAILED = "Encoder failed"
STATUS_NO_TARGET = "No target"
STATUS_NO_FRAMES = "No frames"
STATUS_NO_CHUNKS = "No chunks encoded"
STATUS_FINAL_CHUNK = "Encoding final chunk..."

SIGNALS = ("frame_captured", "status_changed")
EMITTED_SIGNALS = ("status_changed",)

BUS_TOPICS = ()
BUS_EMITS = ()

ACTIONS = {
    "record_button_clicked": "toggle_recording",
    "open_button_clicked": "open_output_folder",
    "flash_timer_tick": "flash_record_button",
    "capture_timer_tick": "capture_frame",
    "recorder_status_changed": "set_status",
}

TIMERS = {
    "capture_timer": "capture_frame",
    "flash_timer": "flash_record_button",
}

STEP_NAMES = ("start", "capture_frame", "stop", "toggle", "open_folder")

SCREEN_ORDER = ("record_button", "open_button", "status_label")


class RecorderWorld:
    """What the machine offers a capture run, handed in rather than read.

    ``has_cv2``, ``has_ffmpeg`` and ``has_pillow`` decide the engine.
    ``grabs`` is what each grab answers in turn: a width and height pair
    for a frame, ``None`` for a device that returned nothing, or an
    exception instance for a device that refused. ``encoder_opens`` is
    whether the direct writer opened. ``encode_returncode`` and
    ``concat_returncode`` are what the chunk encoder and the joiner
    answered. ``write_error`` stands for a disk that cannot take another
    frame; ``build_error`` for an output folder that cannot be made.
    """

    def __init__(
        self,
        has_cv2: bool = False,
        has_ffmpeg: bool = False,
        has_pillow: bool = False,
        grabs: Any = (),
        encoder_opens: bool = True,
        encode_returncode: int = 0,
        concat_returncode: int = 0,
        write_error: Exception | None = None,
        build_error: Exception | None = None,
        gif_save_error: Exception | None = None,
        move_error: Exception | None = None,
        cwd: str = "",
        platform: str = "linux",
    ):
        self.has_cv2 = has_cv2
        self.has_ffmpeg = has_ffmpeg
        self.has_pillow = has_pillow
        self.grabs = list(grabs)
        self.encoder_opens = encoder_opens
        self.encode_returncode = encode_returncode
        self.concat_returncode = concat_returncode
        self.write_error = write_error
        self.build_error = build_error
        self.gif_save_error = gif_save_error
        self.move_error = move_error
        self.cwd = cwd
        self.platform = platform
        self.grab_calls = 0
        self.made_dirs: list[str] = []
        self.written_files: list[str] = []
        self.deleted_files: list[str] = []
        self.commands: list[tuple] = []

    def grab(self):
        """The next grab this world answers, or the last one for ever."""
        if not self.grabs:
            answer = None
        elif self.grab_calls < len(self.grabs):
            answer = self.grabs[self.grab_calls]
        else:
            answer = self.grabs[-1]
        self.grab_calls += 1
        if isinstance(answer, BaseException):
            raise answer
        return answer


def choose_engine(has_cv2: bool, has_ffmpeg: bool, has_pillow: bool) -> str:
    """The engine a machine with these three answers records with."""
    if has_cv2:
        return CV2
    if has_ffmpeg:
        return FFMPEG
    if has_pillow:
        return GIF
    return PNG


def engine_tip(engine: str) -> str:
    """The record button's tip for `engine`, or the plain word."""
    return ENGINE_TIPS.get(engine, FALLBACK_TIP)


def engine_colour(engine: str) -> str:
    """The colour the toolbar shows `engine` in."""
    return ENGINE_COLOURS.get(engine, GREY)


def capture_interval_ms(fps: int) -> int:
    """The capture timer's delay for `fps`, never under one millisecond."""
    return max(1, 1000 // fps)


def capture_interval_fits_timer(fps: int) -> bool:
    """Whether the delay `fps` asks for is one a timer can hold.

    The delay is a signed 32-bit count of milliseconds. A frame rate
    under one frame per ``TIMER_MAX_MS`` asks for more than that, and the
    screen shows the rate as out of range rather than starting a run.
    """
    delay = capture_interval_ms(fps)
    return delay <= TIMER_MAX_MS


def chunk_frames(fps: int) -> int:
    """How many frames one rolling chunk holds at `fps`."""
    return max(1, CHUNK_SECONDS * fps)


def gif_frame_ms(fps: int) -> int:
    """How long one sampled GIF frame shows, never under 50 ms."""
    return max(GIF_MIN_FRAME_MS, int(1000 / (fps / GIF_SAMPLE_RATE)))


def default_output_dir(base: str) -> str:
    """The recordings folder under `base`, written with forward slashes."""
    return "/".join((base.rstrip("/"),) + DEFAULT_OUTPUT_PARTS)


def output_name(engine: str, stamp: str) -> str:
    """The file one run of `engine` writes, named for `stamp`."""
    suffix = GIF_SUFFIX if engine == GIF else VIDEO_SUFFIX
    return f"{OUTPUT_STEM}{stamp}{suffix}"


def frame_dir_name(stamp: str) -> str:
    """The folder the PNG frames of the run stamped `stamp` go in."""
    return f"{FRAME_DIR_STEM}{stamp}"


def chunk_dir_name(stamp: str) -> str:
    """The folder the encoded chunks of the run stamped `stamp` go in."""
    return f"{CHUNK_DIR_STEM}{stamp}"


def frame_name(index: int) -> str:
    """The file one captured frame is written to."""
    return FRAME_NAME_FORMAT.format(index=index)


def chunk_name(index: int) -> str:
    """The file one encoded chunk is written to."""
    return CHUNK_NAME_FORMAT.format(index=index)


def encode_command(
    frame_dir: str, chunk_path: str, fps: int, frame_start: int, frame_count: int
) -> tuple:
    """The program and arguments that encode one chunk. Nothing is run."""
    return (
        FFMPEG_BINARY,
        "-y",
        "-framerate",
        str(fps),
        "-start_number",
        str(frame_start),
        "-i",
        f"{frame_dir}/{FFMPEG_FRAME_PATTERN}",
        "-frames:v",
        str(frame_count),
        "-c:v",
        VIDEO_CODEC,
        "-pix_fmt",
        PIXEL_FORMAT,
        "-movflags",
        MOVIE_FLAGS,
        chunk_path,
    )


def concat_command(list_path: str, output_path: str) -> tuple:
    """The program and arguments that join the chunks. Nothing is run."""
    return (
        FFMPEG_BINARY,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        list_path,
        "-c",
        "copy",
        output_path,
    )


def concat_list_text(chunk_paths) -> str:
    """The joiner's input list, one line per chunk."""
    return "".join("file '" + path + "'\n" for path in chunk_paths)


def open_folder_request(output_dir: str, platform: str, cwd: str) -> tuple:
    """The command and folder the open button asks for. Nothing is run.

    An empty ``output_dir`` resolves to `cwd`. That is what the shipped
    toolbar does: it never fills in the recorder's own default.
    """
    folder = output_dir or cwd
    return (OPEN_COMMANDS.get(platform, OPEN_COMMANDS["linux"]), folder)


def button_style(background: str, foreground: str, border: str, hover: str) -> str:
    """The record and open buttons' style sheet."""
    return (
        f"QPushButton{{background:{background};color:{foreground};"
        f"border:1px solid {border};border-radius:{BUTTON_RADIUS_PX}px;"
        f"font-size:{BUTTON_FONT_PX}px;font-weight:bold;"
        f"padding:{BUTTON_PADDING};"
        f"font-family:{FONT_FAMILY};}}"
        f"QPushButton:hover{{border-color:{hover};}}"
    )


def flash_style(background: str) -> str:
    """The record button's style while it flashes. It names no hover."""
    return (
        f"QPushButton{{background:{background};color:{RED};"
        f"border:1px solid {RED};border-radius:{BUTTON_RADIUS_PX}px;"
        f"font-size:{BUTTON_FONT_PX}px;font-weight:bold;"
        f"padding:{BUTTON_PADDING};"
        f"font-family:{FONT_FAMILY};}}"
    )


def status_style(colour: str) -> str:
    """The status label's style sheet in `colour`."""
    return (
        f"color:{colour};font-size:{STATUS_FONT_PX}px;"
        f"font-family:{FONT_FAMILY};background:transparent;"
    )


def flash_background(is_lit: bool) -> str:
    """The record button's background on one flash tick."""
    return FLASH_BG if is_lit else BG


def basename(path: str) -> str:
    """The last part of a forward-slash path."""
    return path.rsplit("/", 1)[-1]


class Capture:
    """One recording run, holding no device and writing no file.

    ``start`` picks the engine from the world, names the output and
    reports whether the run began. ``capture_frame`` advances one tick.
    ``stop`` closes the run and returns the output it names. Every file
    the run would write, make or delete is recorded on the world as text.
    """

    def __init__(self, world: RecorderWorld, fps: int = DEFAULT_FPS, output_dir=""):
        if world.build_error is not None:
            raise world.build_error
        self.world = world
        self.fps = fps
        self.output_dir = output_dir
        self.target = None
        world.made_dirs.append(output_dir)
        self.engine = choose_engine(world.has_cv2, world.has_ffmpeg, world.has_pillow)
        self.is_recording = False
        self.frame_n = 0
        self.last_output = ""
        self.interval_ms = 0
        self.statuses: list[tuple] = []
        self.frame_dir = ""
        self.chunk_dir = ""
        self.chunks: list[str] = []
        self.chunk_n = 0
        self.chunk_frame_start = 0
        self.gif_frames: list = []
        self.writer_open = False
        self.stream_writes = 0
        self.stopped_moves: list[tuple] = []

    def _say(self, message: str, colour: str) -> None:
        self.statuses.append((message, colour))

    @property
    def chunk_frames(self) -> int:
        """How many frames one rolling chunk of this run holds."""
        return chunk_frames(self.fps)

    def _grab(self):
        try:
            return self.world.grab()
        except Exception:
            return None

    def start(self, stamp: str) -> bool:
        """Begin a run stamped `stamp`. False when the world refused."""
        if self.is_recording:
            return False
        self.last_output = f"{self.output_dir}/{output_name(self.engine, stamp)}"
        if self.engine == FFMPEG:
            self.frame_dir = f"{self.output_dir}/{frame_dir_name(stamp)}"
            self.chunk_dir = f"{self.output_dir}/{chunk_dir_name(stamp)}"
            self.world.made_dirs.append(self.frame_dir)
            self.world.made_dirs.append(self.chunk_dir)
            self.chunks = []
            self.chunk_n = 0
            self.chunk_frame_start = 0
        elif self.engine == PNG:
            self.frame_dir = f"{self.output_dir}/{frame_dir_name(stamp)}"
            self.world.made_dirs.append(self.frame_dir)
            self.chunk_frame_start = 0
            self.last_output = self.frame_dir
        elif self.engine == GIF:
            self.gif_frames = []
        frame = self._grab()
        if frame is None:
            self._say(STATUS_GRAB_FAILED, RED)
            return False
        if self.engine == CV2 and not self.world.encoder_opens:
            self._say(STATUS_ENCODER_FAILED, RED)
            return False
        self.writer_open = self.engine == CV2
        self.is_recording = True
        self.frame_n = 0
        self.interval_ms = capture_interval_ms(self.fps)
        self._say(STATUS_START, RED)
        return True

    def capture_frame(self, elapsed_s: int = 0) -> None:
        """Advance one capture tick. Does nothing when the run is over."""
        if not self.is_recording:
            return
        frame = self._grab()
        if frame is None:
            return
        if self.engine == CV2:
            self.stream_writes += 1
        elif self.engine == FFMPEG:
            self._write(f"{self.frame_dir}/{frame_name(self.frame_n)}")
            in_chunk = self.frame_n - self.chunk_frame_start + 1
            if in_chunk >= self.chunk_frames:
                start = self.chunk_frame_start
                self.chunk_frame_start = self.frame_n + 1
                self._encode_chunk(start, in_chunk)
        elif self.engine == GIF:
            if self.frame_n % GIF_SAMPLE_RATE == 0:
                width, height = frame
                self.gif_frames.append(
                    (width // GIF_RESIZE_DIVISOR, height // GIF_RESIZE_DIVISOR)
                )
                if len(self.gif_frames) > MAX_GIF_FRAMES:
                    self.gif_frames.pop(0)
        else:
            self._write(f"{self.frame_dir}/{frame_name(self.frame_n)}")
            oldest = self.frame_n - self.chunk_frames
            if oldest >= 0:
                self.world.deleted_files.append(
                    f"{self.frame_dir}/{frame_name(oldest)}"
                )
        self.frame_n += 1
        if self.frame_n % (max(1, self.fps) * 2) == 0:
            self._say(f"● REC  {elapsed_s}s  ({self.frame_n}f)", RED)

    def _write(self, path: str) -> None:
        if self.world.write_error is not None:
            return
        self.world.written_files.append(path)

    def _encode_chunk(self, frame_start: int, frame_count: int) -> str:
        if not self.frame_dir or not self.chunk_dir:
            return ""
        path = f"{self.chunk_dir}/{chunk_name(self.chunk_n)}"
        self.chunk_n += 1
        self.world.commands.append(
            encode_command(self.frame_dir, path, self.fps, frame_start, frame_count)
        )
        if self.world.encode_returncode != 0:
            return ""
        for index in range(frame_start, frame_start + frame_count):
            self.world.deleted_files.append(f"{self.frame_dir}/{frame_name(index)}")
        self.chunks.append(path)
        return path

    def stop(self, elapsed_s: float) -> str:
        """Close the run and return the output it names."""
        if not self.is_recording:
            return self.last_output
        self.is_recording = False
        if self.engine == CV2:
            self.writer_open = False
            self._say(f"Saved {basename(self.last_output)}", GREEN)
        elif self.engine == FFMPEG:
            self._stop_ffmpeg()
        elif self.engine == GIF:
            self._stop_gif()
        else:
            self._stop_png()
        return self.last_output

    def _stop_ffmpeg(self) -> None:
        remaining = self.frame_n - self.chunk_frame_start
        if remaining > 0 and self.frame_dir:
            self._say(STATUS_FINAL_CHUNK, GOLD)
            self._encode_chunk(self.chunk_frame_start, remaining)
        if self.frame_dir:
            self.stopped_moves.append(("rmtree", self.frame_dir))
        self.frame_dir = ""
        if not self.chunks:
            self._say(STATUS_NO_CHUNKS, RED)
            return
        if len(self.chunks) == 1:
            self.stopped_moves.append(("move", self.chunks[0], self.last_output))
            if self.world.move_error is None:
                self.stopped_moves.append(("rmtree", self.chunk_dir))
                self._say(f"Saved {basename(self.last_output)}", GREEN)
            else:
                self.last_output = self.chunks[0]
                self._say(f"Saved {basename(self.chunks[0])}", GREEN)
        else:
            self._say(f"Joining {len(self.chunks)} chunks...", GOLD)
            list_path = f"{self.chunk_dir}/{CONCAT_LIST_NAME}"
            self.world.written_files.append(list_path)
            self.world.commands.append(concat_command(list_path, self.last_output))
            joined = self.world.concat_returncode == 0
            self.stopped_moves.append(("rmtree", self.chunk_dir))
            if joined:
                self._say(f"Saved {basename(self.last_output)}", GREEN)
            else:
                self.last_output = self.chunks[0]
                self._say(f"Partial: {basename(self.chunks[0])}", GOLD)
        self.chunks = []
        self.chunk_dir = ""

    def _stop_gif(self) -> None:
        if not self.gif_frames:
            self._say(STATUS_NO_FRAMES, RED)
            return
        self._say(f"Writing GIF ({len(self.gif_frames)}f)...", GOLD)
        error = self.world.gif_save_error
        if error is None:
            self.world.written_files.append(self.last_output)
            self._say(f"Saved {basename(self.last_output)}", GREEN)
        else:
            self._say(f"GIF failed: {error}", RED)
        self.gif_frames = []

    def _stop_png(self) -> None:
        prefix = self.frame_dir + "/"
        kept = [
            path
            for path in self.world.written_files
            if path.startswith(prefix) and path not in self.world.deleted_files
        ]
        self._say(f"{len(kept)}f → {basename(self.frame_dir)}/", GOLD)
        self.frame_dir = ""


class ToolbarModel:
    """The recorder toolbar: two buttons, a status label and a layout."""

    def __init__(self, world: RecorderWorld, fps: int = DEFAULT_FPS, output_dir=""):
        self.world = world
        self.fps = fps
        self.output_dir = output_dir
        self.engine = choose_engine(world.has_cv2, world.has_ffmpeg, world.has_pillow)
        self.capture: Capture | None = None
        self.is_lit = False
        self.record_label = REC_LABEL
        self.record_style = button_style(BG, RED, RED, CYAN)
        self.status_text = self.engine
        self.status_colour = engine_colour(self.engine)
        self.flash_running = False
        self.target = None
        self.last_output = ""

    def set_target(self, target) -> None:
        """Point the toolbar, and any live run, at another widget."""
        self.target = target
        if self.capture is not None:
            self.capture.target = target

    def set_status(self, message: str, colour: str = "") -> None:
        """Show `message`, keeping the last colour when none is given."""
        self.status_text = message
        if colour:
            self.status_colour = colour

    def flash_record_button(self) -> str:
        """Advance one flash tick and return the style now shown."""
        self.is_lit = not self.is_lit
        self.record_style = flash_style(flash_background(self.is_lit))
        return self.record_style

    def toggle_recording(self, stamp: str = "", elapsed_s: float = 0.0):
        """Start a run, or stop the one running. Returns what it did."""
        if self.capture is not None and self.capture.is_recording:
            return self.stop_recording(elapsed_s)
        return self.start_recording(stamp)

    def start_recording(self, stamp: str):
        """Build a run and start it. Refuses when there is no target."""
        if self.target is None:
            self.set_status(STATUS_NO_TARGET, RED)
            return False
        capture = Capture(self.world, fps=self.fps, output_dir=self.output_dir)
        capture.target = self.target
        started = capture.start(stamp)
        for message, colour in capture.statuses:
            self.set_status(message, colour)
        if started:
            self.capture = capture
            self.record_label = STOP_LABEL
            self.record_style = button_style(RECORDING_BG, RED, RED, CYAN)
            self.flash_running = True
        else:
            self.capture = None
        return started

    def stop_recording(self, elapsed_s: float) -> str:
        """Stop the run and put the record button back.

        Returns the output the run named, which the shipped widget drops.
        """
        self.flash_running = False
        self.is_lit = False
        self.record_label = REC_LABEL
        self.record_style = button_style(BG, RED, RED, CYAN)
        if self.capture is None:
            return self.last_output
        already_said = len(self.capture.statuses)
        self.last_output = self.capture.stop(elapsed_s)
        for message, colour in self.capture.statuses[already_said:]:
            self.set_status(message, colour)
        self.capture = None
        return self.last_output

    def open_output_folder(self):
        """The command and folder the open button asks for."""
        return open_folder_request(self.output_dir, self.world.platform, self.world.cwd)

    def build(self) -> dict:
        """The whole toolbar as one serialisable screen."""
        return {
            "engine": self.engine,
            "fps": self.fps,
            "capture_interval_ms": capture_interval_ms(self.fps),
            "flash_interval_ms": FLASH_INTERVAL_MS,
            "chunk_frames": chunk_frames(self.fps),
            "flash_running": self.flash_running,
            "is_recording": bool(self.capture and self.capture.is_recording),
            "layout": {
                "margins_px": list(LAYOUT_MARGINS_PX),
                "spacing_px": LAYOUT_SPACING_PX,
                "order": list(SCREEN_ORDER),
            },
            "record_button": {
                "text": self.record_label,
                "fixed_height_px": BUTTON_HEIGHT_PX,
                "tooltip": engine_tip(self.engine),
                "style": self.record_style,
            },
            "open_button": {
                "text": OPEN_LABEL,
                "fixed_width_px": OPEN_BUTTON_WIDTH_PX,
                "fixed_height_px": OPEN_BUTTON_HEIGHT_PX,
                "tooltip": OPEN_TIP,
                "style": button_style(BG, GREY, BORDER, CYAN),
            },
            "status_label": {
                "text": self.status_text,
                "colour": self.status_colour,
                "fixed_height_px": BUTTON_HEIGHT_PX,
                "minimum_width_px": STATUS_MIN_WIDTH_PX,
                "style": status_style(self.status_colour),
            },
        }


def toolbar_state(toolbar: ToolbarModel) -> dict:
    """What a reader sees on the toolbar right now."""
    return {
        "status": toolbar.status_text,
        "status_style": status_style(toolbar.status_colour),
        "record_label": toolbar.record_label,
        "record_style": toolbar.record_style,
        "flash_running": toolbar.flash_running,
    }


def run_steps(toolbar: ToolbarModel, steps) -> list:
    """Drive `steps` in order and report each one.

    Each step is a name from ``STEP_NAMES``, or that name paired with the
    stamp or elapsed seconds it carries. Each report names the step's
    index, its name, the refusal type it raised or None, and what the
    toolbar shows after it. A step that raises ends the sequence.
    """
    report = []
    for index, step in enumerate(steps):
        name, argument = step if isinstance(step, tuple) else (step, None)
        refusal = None
        try:
            _run_one_step(toolbar, name, argument)
        except Exception as exc:
            refusal = type(exc).__name__
        report.append(
            dict(index=index, step=name, refusal=refusal, **toolbar_state(toolbar))
        )
        if refusal is not None:
            break
    return report


def _run_one_step(toolbar: ToolbarModel, name: str, argument):
    if name == "start":
        return toolbar.start_recording(argument or "")
    if name == "capture_frame":
        if toolbar.capture is None:
            return None
        before = len(toolbar.capture.statuses)
        toolbar.capture.capture_frame(int(argument or 0))
        for message, colour in toolbar.capture.statuses[before:]:
            toolbar.set_status(message, colour)
        return toolbar.capture.frame_n
    if name == "stop":
        return toolbar.stop_recording(argument or 0.0)
    if name == "toggle":
        return toolbar.toggle_recording(argument or "")
    if name == "open_folder":
        return list(toolbar.open_output_folder())
    raise LookupError(name)


def build_view_model(
    has_cv2: bool = False,
    has_ffmpeg: bool = False,
    has_pillow: bool = False,
    fps: int = DEFAULT_FPS,
    output_dir: str = "",
) -> dict:
    """The toolbar screen a machine with these answers paints."""
    world = RecorderWorld(has_cv2=has_cv2, has_ffmpeg=has_ffmpeg, has_pillow=has_pillow)
    return ToolbarModel(world, fps=fps, output_dir=output_dir).build()


def view_model(params: dict) -> dict:
    """The bridge handler for ``screen_recorder.state``."""
    params = params or {}
    return {
        "screen": build_view_model(
            has_cv2=bool(params.get("has_cv2", False)),
            has_ffmpeg=bool(params.get("has_ffmpeg", False)),
            has_pillow=bool(params.get("has_pillow", False)),
            fps=int(params.get("fps", DEFAULT_FPS)),
            output_dir=str(params.get("output_dir", "")),
        ),
        "engines": list(ENGINES),
        "engine_tips": dict(ENGINE_TIPS),
        "engine_colours": dict(ENGINE_COLOURS),
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "signals": list(SIGNALS),
        "bus_topics": list(BUS_TOPICS),
    }
