"""The shipped audio suite and the Qt-free surface, side by side.

A failure means the view model carries a different preset table, a
different key multiplier, a different tone sample, a different file
name, a different status line, a different caption, a different volume,
a different layer count or a different refusal than ``src.gui.audio_suite``
ships.

No audio device is opened and nothing is played. The player, the audio
output and the file chooser are stood in for on every run. The tone
generator is driven for real at a short length, so the sound itself is
compared sample by sample against frames the shipped code wrote.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import wave
from contextlib import contextmanager
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui import audio_suite as shipped
from src.gui.main_tabs import audio_suite_surface as surface

REPO_ROOT = Path(__file__).resolve().parents[1]

SHIPPED_PATH = REPO_ROOT / "src/gui/audio_suite.py"
SURFACE_PATH = REPO_ROOT / "src/gui/main_tabs/audio_suite_surface.py"
BRIDGE_PATH = REPO_ROOT / "src/core/desktop_bridge.py"
WIRED_NEIGHBOUR_PATH = REPO_ROOT / "src/gui/widgets/privacy_dot.py"
SIGNAL_NEIGHBOUR_PATH = REPO_ROOT / "src/gui/launcher.py"
TIMER_NEIGHBOUR_PATH = REPO_ROOT / "src/gui/history_tab.py"
TIMER_NAMESAKE_PATH = REPO_ROOT / "src/gui/main_tabs/history_tab.py"
BUS_NEIGHBOUR_PATH = REPO_ROOT / "src/gui/bot_visualizer.py"
SCREEN_NEIGHBOUR_PATH = REPO_ROOT / "src/gui/widgets/dashboard_stat_card.py"
NESTED_CLASS_NEIGHBOUR_PATH = REPO_ROOT / "src/gui/stock_main_window.py"
READ_ONLY_NEIGHBOUR_PATH = REPO_ROOT / "src/gui/indicator_panel.py"

METHOD_NAME = "audio_suite.state"

# One length short enough to drive the real generator many times. The
# loop join is two seconds whatever the length, so the frames written
# are all inside it and every one is a blended frame.
SHORT_DURATION_S = 0.001

# The three states the sound library and the device can be in.
MEDIA_READY = "ready"
MEDIA_DEVICE_REFUSED = "device_refused"
MEDIA_LIBRARY_MISSING = "library_missing"
ALL_MEDIA_STATES = (MEDIA_READY, MEDIA_DEVICE_REFUSED, MEDIA_LIBRARY_MISSING)

# Every preset the shipped table holds, in the order it builds them.
EXPECTED_PRESET_NAMES = (
    "Deep Space",
    "Theta Waves",
    "Crystal Cave",
    "Ocean Floor",
    "Quantum Field",
    "Solar Wind",
    "Meditation Bell",
    "White Noise Pad",
)

# Every musical key, in the order the shipped table builds them.
EXPECTED_KEY_NAMES = (
    "C",
    "C#",
    "D",
    "D#",
    "E",
    "F",
    "F#",
    "G",
    "G#",
    "A",
    "A#",
    "B",
)

# Every key multiplier, typed out here rather than read from either
# module. Neither side can satisfy this table by copying the other.
EXPECTED_KEY_MULTIPLIERS = {
    "C": 1.0,
    "C#": 1.05946,
    "D": 1.12246,
    "D#": 1.18921,
    "E": 1.25992,
    "F": 1.33484,
    "F#": 1.41421,
    "G": 1.49831,
    "G#": 1.58740,
    "A": 1.68179,
    "A#": 1.78180,
    "B": 1.88775,
}

# Every interval and loudness pair of every preset, typed out here too.
EXPECTED_PRESETS = {
    "Deep Space": [
        [1.0, 0.30],
        [1.5, 0.15],
        [2.0, 0.10],
        [3.0, 0.05],
        [1.003, 0.10],
    ],
    "Theta Waves": [[1.0, 0.20], [1.03, 0.20], [0.5, 0.10], [0.515, 0.10]],
    "Crystal Cave": [
        [1.0, 0.15],
        [1.222, 0.10],
        [1.479, 0.08],
        [0.5, 0.12],
        [0.611, 0.06],
    ],
    "Ocean Floor": [
        [1.0, 0.25],
        [1.5, 0.15],
        [2.0, 0.10],
        [1.007, 0.15],
        [3.0, 0.05],
    ],
    "Quantum Field": [
        [1.0, 0.20],
        [2.0, 0.10],
        [0.5, 0.15],
        [1.002, 0.10],
        [1.5, 0.08],
    ],
    "Solar Wind": [
        [1.0, 0.15],
        [1.636, 0.10],
        [2.273, 0.08],
        [1.002, 0.10],
        [0.5, 0.12],
    ],
    "Meditation Bell": [
        [1.0, 0.20],
        [2.0, 0.08],
        [3.0, 0.04],
        [0.5, 0.10],
        [1.001, 0.05],
    ],
    "White Noise Pad": [
        [1.0, 0.05],
        [2.0, 0.05],
        [3.0, 0.04],
        [4.0, 0.03],
        [5.0, 0.03],
    ],
}

EXPECTED_BASE_FREQUENCIES = [
    ["27.5Hz", 27.5],
    ["55Hz", 55],
    ["110Hz", 110],
    ["220Hz", 220],
]

PRESET_TOTAL = 8
KEY_TOTAL = 12
LAYER_TOTAL = 4
BASE_FREQUENCY_TOTAL = 4

# Counted from the parsed shipped file, both timer forms, both bus
# directions. Every number below is asserted against a counter that runs
# over the syntax tree, never over the text.
SHIPPED_CLASS_TOTAL = 7
SHIPPED_REACHABLE_CLASS_TOTAL = 6
SHIPPED_METHOD_TOTAL = 29
SHIPPED_MODULE_FUNCTION_TOTAL = 1
SHIPPED_SIGNAL_TOTAL = 2
SHIPPED_CONNECT_TOTAL = 17
SHIPPED_TIMER_BUILT_TOTAL = 1
SHIPPED_TIMER_SINGLE_SHOT_TOTAL = 0
SHIPPED_THREAD_TOTAL = 0
SHIPPED_BUS_SUBSCRIBE_TOTAL = 0
SHIPPED_BUS_EMIT_TOTAL = 0
SHIPPED_SIGNAL_EMIT_TOTAL = 5
SHIPPED_SCREEN_ELEMENT_TOTAL = 34

# The controls. Each is a file that really carries one of the things the
# counter above reports none of in the surface.
WIRED_NEIGHBOUR_CONNECTS = 1
SIGNAL_NEIGHBOUR_SIGNALS = 3
TIMER_NEIGHBOUR_TIMERS = 1
TIMER_NAMESAKE_TIMERS = 0
BUS_NEIGHBOUR_SUBSCRIBES = 2
BUS_NEIGHBOUR_EMITS = 5
SCREEN_NEIGHBOUR_ELEMENTS = 3
SINGLE_SHOT_NEIGHBOUR_TOTAL = 5

# The names the widened method counter must find, and the one it must
# leave out. A signal is callable and is not a method.
READ_ONLY_MEMBERS = ("_reading_fingerprint", "lock_timeframe", "selected_bot_id")
NESTED_CLASS_NAME = "_StockLogHandler"
EXCLUDED_SIGNAL_NAME = "clicked"

# The awkward names a caller may ask for. None is a preset and none is a
# key.
UNKNOWN_NAMES = {
    "empty": "",
    "zero": "0",
    "negative": "-1",
    "a_thousand_million": "1000000000",
    "one_billionth": "1e-09",
    "infinity": "inf",
    "minus_infinity": "-inf",
    "not_a_number": "nan",
    "unicode": "Δ→⚡",
    "long": "X" * 200,
    "markup": "<b>Deep Space</b>",
    "apostrophe": "it's",
    "uppercase": "DEEP SPACE",
    "spaced": " Deep Space ",
    "newline": "Deep Space\nTheta Waves",
    "dotted": "presets.Deep Space",
    "sharp": "#",
    "private": "_PRESETS",
    "dunder": "__all__",
    "quoted": '"Deep Space"',
}

# The values a caller may send where a name belongs.
NON_STRING_NAMES: tuple = (None, 0, -1, 9.5, True, [], ["C"], {}, (), b"C")

# Every setting a slider may be handed, and what it is.
SLIDER_CASES = {
    "zero": 0,
    "half": 50,
    "full": 100,
    "under": -1,
    "over": 101,
    "far_under": -500,
    "far_over": 500,
    "decimal": 1.5,
    "whole_decimal": 2.0,
    "true": True,
    "false": False,
    "a_thousand_million": 1_000_000_000,
    "largest_taken": 2**31 - 1,
    "one_past_largest": 2**31,
    "smallest_taken": -(2**31),
    "one_past_smallest": -(2**31) - 1,
    "one_billionth": 1e-9,
    "infinity": math.inf,
    "minus_infinity": -math.inf,
    "not_a_number": math.nan,
    "text": "x",
    "number_as_text": "50",
    "nothing": None,
    "bytes": b"50",
    "empty_list": [],
    "empty_table": {},
}

# The music files a caller may add. Each is text a path may really be.
FILE_CASES = {
    "plain": "/music/one.mp3",
    "windows": "C:/music/two.wav",
    "unicode": "/music/Δ→⚡.ogg",
    "long": "/music/" + "X" * 200 + ".flac",
    "markup": "/music/<b>three</b>.m4a",
    "apostrophe": "/music/it's here.mp3",
    "newline": "/music/four\nfive.mp3",
    "no_extension": "/music/six",
    "trailing_slash": "/music/",
    "bare": "seven.mp3",
    "empty": "",
}

REFUSAL_TYPE = "refused"
ANSWER_TYPE = "answered"


# ---------------------------------------------------------------------
# The outward edges, stood in for. Nothing here reaches a device.
# ---------------------------------------------------------------------


class FakeSignal:
    """A signal a stand-in player carries, so a wiring can be recorded."""

    def __init__(self) -> None:
        self.slots: list = []

    def connect(self, slot) -> None:
        self.slots.append(slot)


class FakeAudioOutput:
    """An audio output that keeps the volume and opens no device."""

    def __init__(self) -> None:
        self.volume = None

    def setVolume(self, value) -> None:
        self.volume = value


class RefusingAudioOutput:
    """An audio output that refuses to open, as a host with no device does."""

    def __init__(self) -> None:
        raise RuntimeError("this host opened no audio device")


class FakePlayer:
    """A media player that records what it was asked and plays nothing."""

    class PlaybackState:
        StoppedState = "stopped"
        PlayingState = "playing"

    class MediaStatus:
        EndOfMedia = "end_of_media"
        LoadedMedia = "loaded"
        InvalidMedia = "invalid"

    def __init__(self) -> None:
        self.calls: list = []
        self.output = None
        self.error_text = ""
        self.mediaStatusChanged = FakeSignal()
        self.errorOccurred = FakeSignal()
        self.playbackStateChanged = FakeSignal()

    def setAudioOutput(self, output) -> None:
        self.output = output

    def setSource(self, url) -> None:
        self.calls.append(("setSource", url.toLocalFile()))

    def play(self) -> None:
        self.calls.append(("play",))

    def stop(self) -> None:
        self.calls.append(("stop",))

    def pause(self) -> None:
        self.calls.append(("pause",))

    def errorString(self) -> str:
        return self.error_text

    def play_total(self) -> int:
        """How many times this player was asked to start."""
        return sum(1 for call in self.calls if call[0] == "play")


class FakeChooser:
    """A file chooser that hands back a prepared list and opens no window."""

    paths: list = []

    @classmethod
    def getOpenFileNames(cls, *_args, **_kwargs):
        return (list(cls.paths), "")


def short_generator(real):
    """The real tone generator, asked for a short length instead of thirty
    seconds. Every other argument, and all of the arithmetic, is the
    shipped code's own."""

    def generate_wav(
        preset_name,
        _duration=30.0,
        master_volume=0.5,
        key="C",
        base_freq=55.0,
        detune=1.0,
        lfo_speed=1.0,
        richness=1.0,
    ):
        return real(
            preset_name,
            SHORT_DURATION_S,
            master_volume,
            key,
            base_freq,
            detune,
            lfo_speed,
            richness,
        )

    return staticmethod(generate_wav)


# ---------------------------------------------------------------------
# One world per side. Everything process-wide is swapped and put back.
# ---------------------------------------------------------------------

# Every name on the shipped module that a side sets for itself. Read by
# the isolation tests, so a name added here is watched by them too.
SHARED_NAMES = (
    "_HAS_MEDIA",
    "QMediaPlayer",
    "QAudioOutput",
    "QFileDialog",
    "safe_process_events",
)

_WATCHED: list = []


@contextmanager
def side_world(media, temp_dir, paths=()):
    """Give one side its own player, output, chooser, media state and
    temporary directory, and put every one of them back afterwards.

    The tone generator is pointed at a short length for the duration, so
    the real generator runs without thirty seconds of arithmetic. Every
    swap is undone even when the body raises.
    """
    was = {name: getattr(shipped, name) for name in SHARED_NAMES}
    was_generator = shipped.ToneGenerator.__dict__["generate_wav"]
    was_temp = tempfile.gettempdir
    was_paths = list(FakeChooser.paths)
    shipped.QMediaPlayer = FakePlayer
    shipped.QFileDialog = FakeChooser
    shipped._HAS_MEDIA = media != MEDIA_LIBRARY_MISSING
    shipped.QAudioOutput = (
        RefusingAudioOutput if media == MEDIA_DEVICE_REFUSED else FakeAudioOutput
    )
    shipped.ToneGenerator.generate_wav = short_generator(
        shipped.ToneGenerator.generate_wav
    )
    FakeChooser.paths = list(paths)
    Path(temp_dir).mkdir(parents=True, exist_ok=True)
    tempfile.gettempdir = lambda: str(temp_dir)
    _WATCHED.append({"media": media, "temp_dir": str(temp_dir)})
    try:
        yield
    finally:
        _WATCHED.pop()
        tempfile.gettempdir = was_temp
        shipped.ToneGenerator.generate_wav = was_generator
        FakeChooser.paths = was_paths
        for name, value in was.items():
            setattr(shipped, name, value)


def _class_name(value):
    """The name of a swapped class, or nothing when the build machine has
    no multimedia library and the shipped module left it unset."""
    return "" if value is None else value.__name__


def world_now():
    """What the world holds right now, for a test that watches a swap."""
    return {
        "media_flag": shipped._HAS_MEDIA,
        "player": _class_name(shipped.QMediaPlayer),
        "output": _class_name(shipped.QAudioOutput),
        "temp_dir": tempfile.gettempdir(),
        "event_loop": shipped.safe_process_events.__name__,
        "generator": shipped.ToneGenerator.__dict__["generate_wav"].__class__.__name__,
        "depth": len(_WATCHED),
    }


PRISTINE_WORLD = world_now()


@pytest.fixture(autouse=True)
def world_restored():
    """Put every shared name back before and after every test in this file."""
    yield
    assert _WATCHED == [], _WATCHED
    assert world_now() == PRISTINE_WORLD, world_now()


# ---------------------------------------------------------------------
# The shipped side, driven step by step
# ---------------------------------------------------------------------


def app():
    """The process application object every widget needs."""
    from tests.qt_pixel import ensure_app

    return ensure_app()


class UnknownShippedStep(LookupError):
    """The sequence named a step the shipped driver does not run."""


class ShippedTab:
    """The real audio tab, driven one named step at a time.

    Every step calls a real method directly. Nothing is driven through a
    Qt signal, which catches a failure inside a slot and carries on, so a
    step that raises reaches this driver rather than the log.
    """

    def __init__(self):
        app()
        self.tab = shipped.AudioSuiteTab()
        self.timer_was_active = self.tab._at.isActive()
        self.tab._at.stop()
        self.music = self.tab._mp
        self.drone = self.tab._de
        self.wave = self.tab._wf
        self.drone_states: list = []
        self.drone.drone_state.connect(
            lambda count, key: self.drone_states.append((count, key))
        )
        self.generating_texts: list = []

    def close(self):
        self.tab.close()
        self.tab.deleteLater()

    def layer(self, index):
        """One layer, refusing a position no layer sits at."""
        return self.drone._layers[index]

    def step(self, name, values):
        if name in ("select_preset", "set_layer_volume", "layer_ended", "layer_error"):
            return self._layer_step(name, values)
        if name in (
            "set_detune",
            "set_lfo",
            "set_richness",
            "select_key",
            "select_base",
            "generate_all",
            "stop_all",
            "key_up",
        ):
            return self._drone_step(name, values)
        if name in (
            "add_files",
            "play_index",
            "toggle_music",
            "next_track",
            "music_ended",
            "stop_music",
            "set_music_volume",
        ):
            return self._music_step(name, values)
        if name == "animate":
            self.wave.animate(values[0])
            return None
        raise UnknownShippedStep(name)

    def _layer_step(self, name, values):
        layer = self.layer(values[0])
        if name == "select_preset":
            layer._preset.setCurrentIndex(layer._preset.findData(values[1]))
        elif name == "set_layer_volume":
            layer._volume.setValue(values[1])
            layer._on_vol(layer._volume.value())
        elif name == "layer_ended":
            layer._on_end(FakePlayer.MediaStatus.EndOfMedia)
        elif name == "layer_error":
            layer._on_error("an error the player reported", "")
        return None

    def _drone_step(self, name, values):
        if name == "set_detune":
            self.drone._det.setValue(values[0])
        elif name == "set_lfo":
            self.drone._lfo.setValue(values[0])
        elif name == "set_richness":
            self.drone._rich.setValue(values[0])
        elif name == "select_key":
            self.drone._key.setCurrentIndex(self.drone._key.findData(values[0]))
        elif name == "select_base":
            self.drone._bf.setCurrentIndex(self.drone._bf.findText(values[0]))
        elif name == "generate_all":
            self._watch_generating(self.drone._gen_all)
        elif name == "stop_all":
            self.drone._stop_all()
        elif name == "key_up":
            self._watch_generating(self.drone._key_up)
        return None

    def _music_step(self, name, values):
        if name == "add_files":
            FakeChooser.paths = list(values[0])
            self.music._add()
        elif name == "play_index":
            self.music._pi(values[0])
        elif name == "toggle_music":
            self.music._tog()
        elif name == "next_track":
            self.music._nxt()
        elif name == "music_ended":
            self.music._oe(FakePlayer.MediaStatus.EndOfMedia)
        elif name == "stop_music":
            self.music._stp()
        elif name == "set_music_volume":
            self.music._vol.setValue(values[0])
            self.music._sv(self.music._vol.value())
        return None

    def _watch_generating(self, call):
        """Run `call` and keep the status line as it stood mid-way.

        The panel writes "Generating..." and then hands the event loop a
        turn. That turn is the only moment the transient line is on the
        screen, so it is read there.
        """
        was = shipped.safe_process_events

        def watched(reason="", force=False):
            self.generating_texts.append(self.drone._st.text())
            return was(reason, force)

        shipped.safe_process_events = watched
        try:
            call()
        finally:
            shipped.safe_process_events = was

    def media_state(self):
        """Which of the three states this tab was built in."""
        if not shipped._HAS_MEDIA:
            return MEDIA_LIBRARY_MISSING
        if self.music._player is None:
            return MEDIA_DEVICE_REFUSED
        return MEDIA_READY

    def snapshot(self):
        """Everything on the screen, in the shape the surface reports."""
        media = self.media_state()
        has_controls = media != MEDIA_LIBRARY_MISSING
        return {
            "media": media,
            "layer_presets": [
                self.layer(i)._preset.currentData() for i in range(LAYER_TOTAL)
            ],
            "layer_volumes_pct": [
                self.layer(i)._volume.value() for i in range(LAYER_TOTAL)
            ],
            "layer_volume_labels": [
                self.layer(i)._vl.text() for i in range(LAYER_TOTAL)
            ],
            "layer_playing": [self.layer(i)._playing for i in range(LAYER_TOTAL)],
            "layer_wav_names": [
                os.path.basename(self.layer(i)._wav) for i in range(LAYER_TOTAL)
            ],
            "key_index": self.drone._key.currentIndex(),
            "base_index": self.drone._bf.currentIndex(),
            "detune_pct": self.drone._det.value(),
            "lfo_pct": self.drone._lfo.value(),
            "richness_pct": self.drone._rich.value(),
            "drone_status": self.drone._st.text(),
            "music_files": list(self.music._files),
            "music_row": self.music._pl.currentRow() if has_controls else -1,
            "music_playing": getattr(self.music, "_playing", False),
            "music_volume_pct": (self.music._vol.value() if has_controls else 50),
            "music_button_label": (self.music._pb.text() if has_controls else "Play"),
            "music_caption": (
                self.music._now.text() if has_controls else "Nothing playing"
            ),
            "waveform_layers": self.wave._layers,
            "waveform_key": self.wave._key,
            "waveform_phase": self.wave._phase,
        }


def run_shipped(steps, media, temp_dir, paths=()):
    """Drive the shipped tab through `steps` and report where it stopped."""
    with side_world(media, temp_dir, paths):
        tab = ShippedTab()
        done = []
        try:
            for index, step in enumerate(steps):
                name = step[0]
                values = tuple(step[1]) if len(step) > 1 else ()
                try:
                    tab.step(name, values)
                except UnknownShippedStep:
                    return {
                        "stopped_at_index": index,
                        "stopped_at_step": name,
                        "refusal": "UnknownStep",
                        "steps_done": done,
                        "state": tab.snapshot(),
                    }
                except Exception as refused:
                    return {
                        "stopped_at_index": index,
                        "stopped_at_step": name,
                        "refusal": type(refused).__name__,
                        "steps_done": done,
                        "state": tab.snapshot(),
                    }
                done.append({"index": index, "step": name, "state": tab.snapshot()})
            return {
                "stopped_at_index": -1,
                "stopped_at_step": "",
                "refusal": "",
                "steps_done": done,
                "state": tab.snapshot(),
            }
        finally:
            tab.close()


def run_surface(steps, media):
    """Drive the surface through the same steps."""
    return surface.run_steps(
        [(step[0], tuple(step[1]) if len(step) > 1 else ()) for step in steps],
        media,
    )


# ---------------------------------------------------------------------
# The two sides, read into one shape
# ---------------------------------------------------------------------


def outcome(call, *args):
    """What one side did with a value: answered with what, or refused how."""
    try:
        return {"did": ANSWER_TYPE, "value": repr(call(*args))}
    except Exception as refused:
        return {"did": REFUSAL_TYPE, "error": type(refused).__name__}


def digest(payload):
    """A stable hash over one side's whole answer."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=repr).encode("utf-8")
    ).hexdigest()


def differences(left, right, trail=""):
    """Every place two answers hold a different value, named by its path."""
    found = []
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right), key=repr):
            if key not in left or key not in right:
                found.append("%s/%s" % (trail, key))
                continue
            found.extend(differences(left[key], right[key], "%s/%s" % (trail, key)))
        return found
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            found.append("%s: %d items against %d" % (trail, len(left), len(right)))
            return found
        for position, (one, other) in enumerate(zip(left, right)):
            found.extend(differences(one, other, "%s[%d]" % (trail, position)))
        return found
    if repr(left) != repr(right):
        found.append("%s: %r against %r" % (trail, left, right))
    return found


def shipped_frames(preset, key, base_freq, detune, lfo_speed, richness, volume, folder):
    """Every frame the real generator wrote, read back off its own file."""
    was_temp = tempfile.gettempdir
    Path(folder).mkdir(parents=True, exist_ok=True)
    tempfile.gettempdir = lambda: str(folder)
    try:
        path = shipped.ToneGenerator.generate_wav(
            preset,
            SHORT_DURATION_S,
            volume,
            key,
            base_freq,
            detune,
            lfo_speed,
            richness,
        )
    finally:
        tempfile.gettempdir = was_temp
    with wave.open(path, "r") as handle:
        settings = {
            "channels": handle.getnchannels(),
            "sample_width": handle.getsampwidth(),
            "frame_rate": handle.getframerate(),
            "frames": handle.getnframes(),
        }
        raw = handle.readframes(settings["frames"])
    left = [struct.unpack_from("<h", raw, i * 4)[0] for i in range(settings["frames"])]
    right = [
        struct.unpack_from("<h", raw, i * 4 + 2)[0] for i in range(settings["frames"])
    ]
    return {
        "name": os.path.basename(path),
        "settings": settings,
        "left": left,
        "right": right,
    }


def surface_frames(preset, key, base_freq, detune, lfo_speed, richness, volume):
    """Every frame the surface says the generator writes."""
    total = surface.frame_total(SHORT_DURATION_S)
    return [
        surface.sample_value(
            preset,
            index,
            SHORT_DURATION_S,
            key,
            base_freq,
            detune,
            lfo_speed,
            richness,
            volume,
        )
        for index in range(total)
    ]


# Every tone the two sides are compared on. One row is one whole sound:
# a preset, a key, a base frequency and the three effect numbers.
TONE_CASES = {
    "opening_defaults": ("Deep Space", "C", 55.0, 1.0, 1.0, 0.3, 0.8),
    "no_detune_fast_lfo": ("Theta Waves", "C#", 27.5, 0.0, 3.0, 0.0, 0.5),
    "heavy_detune_slow_lfo": ("White Noise Pad", "B", 220, 2.0, 0.1, 0.3, 0.8),
    "at_the_richness_floor": ("Crystal Cave", "A#", 110, 1.0, 1.0, 0.5, 0.8),
    "just_over_the_floor": ("Crystal Cave", "A#", 110, 1.0, 1.0, 0.5001, 0.8),
    "rich": ("Ocean Floor", "G", 110, 1.5, 2.0, 1.0, 0.8),
    "unknown_preset_and_key": ("no such preset", "zz", 55.0, 1.0, 1.0, 1.0, 0.8),
    "loudest": ("Solar Wind", "F#", 220, 2.0, 3.0, 1.0, 1.0),
    "silent": ("Meditation Bell", "D", 27.5, 1.0, 1.0, 0.0, 0.0),
}

# The richness that first moves a frame. Measured on the shipped
# generator: at 0.500001 every frame is unchanged, at 0.5001 they move.
RICHNESS_UNCHANGED = 0.500001
RICHNESS_MOVED = 0.5001


# ---------------------------------------------------------------------
# The tables, value for value
# ---------------------------------------------------------------------

PRESET_PAIR_CASES = [
    (name, position)
    for name in EXPECTED_PRESET_NAMES
    for position in range(len(EXPECTED_PRESETS[name]))
]


@pytest.mark.parametrize("preset,position", PRESET_PAIR_CASES)
def test_every_preset_pair_carries_the_shipped_value(preset, position):
    """A preset's interval or loudness differs between the two sides."""
    old = list(shipped.ToneGenerator.PRESETS[preset][position])
    new = list(surface.PRESETS[preset][position])
    assert new == old, "%s[%d]: shipped %r, surface %r" % (preset, position, old, new)


@pytest.mark.parametrize("preset,position", PRESET_PAIR_CASES)
def test_every_preset_pair_matches_the_value_typed_here(preset, position):
    """A preset value was changed on both sides together."""
    typed = EXPECTED_PRESETS[preset][position]
    assert list(surface.PRESETS[preset][position]) == typed
    assert list(shipped.ToneGenerator.PRESETS[preset][position]) == typed


@pytest.mark.parametrize("key", EXPECTED_KEY_NAMES)
def test_every_key_multiplier_carries_the_shipped_value(key):
    """A key multiplier differs between the two sides."""
    assert surface.KEY_MULTIPLIERS[key] == shipped.KEY_MULT[key]
    assert surface.KEY_MULTIPLIERS[key] == EXPECTED_KEY_MULTIPLIERS[key]


def test_the_preset_names_and_their_order_match():
    """The presets came back in a different order or a different set."""
    assert list(shipped.ToneGenerator.PRESETS) == list(EXPECTED_PRESET_NAMES)
    assert list(surface.PRESET_NAMES) == list(EXPECTED_PRESET_NAMES)
    assert len(surface.PRESETS) == PRESET_TOTAL


def test_the_key_names_and_their_order_match():
    """The keys came back in a different order or a different set."""
    assert list(shipped.KEY_MULT) == list(EXPECTED_KEY_NAMES)
    assert list(surface.KEY_NAMES) == list(EXPECTED_KEY_NAMES)
    assert len(surface.KEY_MULTIPLIERS) == KEY_TOTAL


def test_the_sample_rate_matches():
    """The two sides write a different number of frames a second."""
    assert surface.SAMPLE_RATE_HZ == shipped.ToneGenerator.SR
    assert surface.SAMPLE_RATE_HZ == 44100


@pytest.mark.parametrize("case", sorted(UNKNOWN_NAMES))
def test_an_unknown_preset_falls_back_on_both_sides(case):
    """An unknown preset picked a different tone on the two sides."""
    name = UNKNOWN_NAMES[case]
    old = shipped.ToneGenerator.PRESETS.get(
        name, shipped.ToneGenerator.PRESETS["Deep Space"]
    )
    new = surface.preset_intervals(name)
    assert [list(pair) for pair in new] == [list(pair) for pair in old], case
    assert surface.has_preset(name) is False, case


@pytest.mark.parametrize("case", sorted(UNKNOWN_NAMES))
def test_an_unknown_key_multiplies_by_one_on_both_sides(case):
    """An unknown key changed the pitch on one side only."""
    name = UNKNOWN_NAMES[case]
    assert surface.key_multiplier(name) == shipped.KEY_MULT.get(name, 1.0)
    assert surface.key_multiplier(name) == 1.0
    assert surface.has_key(name) is False, case


@pytest.mark.parametrize("value", NON_STRING_NAMES)
def test_a_name_that_is_not_text_asks_for_nothing(value):
    """A number or a list read as a name instead of as no name at all."""
    assert surface.requested_name(value) == ""
    assert surface.has_preset(value) is False
    assert surface.has_key(value) is False


def test_a_name_a_table_cannot_be_keyed_by_refuses_on_both_sides():
    """An unhashable name answered on one side and refused on the other."""
    for unhashable in ([], {}, set(), ["C"]):
        old = outcome(lambda v: shipped.KEY_MULT.get(v, 1.0), unhashable)
        new = outcome(surface.key_multiplier, unhashable)
        assert new == old, (unhashable, old, new)
        assert new["did"] == REFUSAL_TYPE, unhashable
        assert new["error"] == "TypeError", unhashable


def test_a_whole_number_and_a_decimal_are_told_apart():
    """A whole number and a decimal read alike, so a swap went unseen."""
    assert 55 == 55.0
    assert repr(55) != repr(55.0)
    assert digest({"base": repr(55)}) != digest({"base": repr(55.0)})
    assert surface.BASE_FREQUENCIES[1][1] == 55
    assert repr(surface.BASE_FREQUENCIES[1][1]) == "55"
    assert repr(surface.BASE_FREQUENCIES[0][1]) == "27.5"


def test_two_not_a_numbers_are_compared_as_text():
    """Not-a-number compared to itself reported a difference that is not one."""
    assert math.nan != math.nan
    assert repr(math.nan) == repr(math.nan)
    assert differences(math.nan, math.nan) == []
    assert differences(math.nan, 1.0) != []


def test_every_number_of_a_preset_is_read_as_its_own_text():
    """Two numbers of one preset were swapped and nothing reported it."""
    for name, rows in EXPECTED_PRESETS.items():
        for position, pair in enumerate(rows):
            interval, loudness = pair
            live = surface.PRESETS[name][position]
            assert repr(live[0]) == repr(interval), (name, position)
            assert repr(live[1]) == repr(loudness), (name, position)
    swapped = dict(EXPECTED_PRESETS)
    swapped["Deep Space"] = [[0.30, 1.0]] + EXPECTED_PRESETS["Deep Space"][1:]
    assert differences(EXPECTED_PRESETS, swapped) != []


# ---------------------------------------------------------------------
# The tone, sample by sample, against frames the shipped code wrote
# ---------------------------------------------------------------------


@pytest.mark.parametrize("case", sorted(TONE_CASES))
def test_the_two_sides_write_the_same_tone(case, tmp_path):
    """The surface reports a different sound than the generator writes."""
    preset, key, base, detune, lfo, richness, volume = TONE_CASES[case]
    old = shipped_frames(
        preset, key, base, detune, lfo, richness, volume, tmp_path / "old"
    )
    new = surface_frames(preset, key, base, detune, lfo, richness, volume)
    assert old["left"] == new, (
        case,
        old["left"][:6],
        new[:6],
        next(
            (i for i, (a, b) in enumerate(zip(old["left"], new)) if a != b),
            None,
        ),
    )


@pytest.mark.parametrize("case", sorted(TONE_CASES))
def test_both_channels_carry_one_tone(case, tmp_path):
    """The two channels of the written file carry different sounds."""
    preset, key, base, detune, lfo, richness, volume = TONE_CASES[case]
    old = shipped_frames(
        preset, key, base, detune, lfo, richness, volume, tmp_path / "old"
    )
    assert old["left"] == old["right"], case


@pytest.mark.parametrize("case", sorted(TONE_CASES))
def test_the_written_file_carries_the_settings_the_surface_reports(case, tmp_path):
    """The file was written with a different shape than the surface reports."""
    preset, key, base, detune, lfo, richness, volume = TONE_CASES[case]
    old = shipped_frames(
        preset, key, base, detune, lfo, richness, volume, tmp_path / "old"
    )
    assert old["settings"]["channels"] == surface.CHANNEL_TOTAL
    assert old["settings"]["sample_width"] == surface.SAMPLE_WIDTH_BYTES
    assert old["settings"]["frame_rate"] == surface.SAMPLE_RATE_HZ
    assert old["settings"]["frames"] == surface.frame_total(SHORT_DURATION_S)


def test_two_different_real_tones_do_not_match(tmp_path):
    """The tone comparison passes whatever the second side reports.

    Two real tones, one taken from each side. A pass proves the
    comparison reports a difference, so the matches above are not green
    by being unable to fail.
    """
    old = shipped_frames("Deep Space", "C", 55.0, 1.0, 1.0, 0.3, 0.8, tmp_path / "a")
    new = surface_frames("Ocean Floor", "G", 110, 1.5, 2.0, 1.0, 0.8)
    assert old["left"] != new
    other = shipped_frames("Ocean Floor", "G", 110, 1.5, 2.0, 1.0, 0.8, tmp_path / "b")
    first = surface_frames("Deep Space", "C", 55.0, 1.0, 1.0, 0.3, 0.8)
    assert other["left"] != first
    assert other["left"] == surface_frames("Ocean Floor", "G", 110, 1.5, 2.0, 1.0, 0.8)


def test_the_same_tone_twice_matches(tmp_path):
    """The comparison moves between two runs over one input."""
    first = shipped_frames("Deep Space", "C", 55.0, 1.0, 1.0, 0.3, 0.8, tmp_path / "a")
    second = shipped_frames("Deep Space", "C", 55.0, 1.0, 1.0, 0.3, 0.8, tmp_path / "b")
    assert first["left"] == second["left"]
    assert surface_frames("Deep Space", "C", 55.0, 1.0, 1.0, 0.3, 0.8) == (
        surface_frames("Deep Space", "C", 55.0, 1.0, 1.0, 0.3, 0.8)
    )


def test_the_richness_floor_is_where_the_shipped_generator_puts_it(tmp_path):
    """The extra harmonic starts at a different richness on the two sides.

    Measured on the shipped generator: a richness of 0.500001 leaves
    every written frame where a richness of 0.5 put it, and 0.5001 moves
    them. A boundary written from memory would pass on the wrong side of
    it.
    """
    at_floor = shipped_frames(
        "Deep Space", "C", 55.0, 1.0, 1.0, surface.RICHNESS_FLOOR, 0.8, tmp_path / "a"
    )
    unchanged = shipped_frames(
        "Deep Space", "C", 55.0, 1.0, 1.0, RICHNESS_UNCHANGED, 0.8, tmp_path / "b"
    )
    moved = shipped_frames(
        "Deep Space", "C", 55.0, 1.0, 1.0, RICHNESS_MOVED, 0.8, tmp_path / "c"
    )
    assert at_floor["left"] == unchanged["left"]
    assert at_floor["left"] != moved["left"]
    assert surface_frames("Deep Space", "C", 55.0, 1.0, 1.0, RICHNESS_MOVED, 0.8) == (
        moved["left"]
    )
    assert (
        surface_frames("Deep Space", "C", 55.0, 1.0, 1.0, surface.RICHNESS_FLOOR, 0.8)
        == at_floor["left"]
    )


def test_a_tone_at_no_volume_is_silent(tmp_path):
    """A tone asked for at no volume still carries sound."""
    old = shipped_frames(
        "Deep Space", "C", 55.0, 1.0, 1.0, 1.0, 0.0, tmp_path / "silent"
    )
    assert set(old["left"]) == {0}
    assert set(surface_frames("Deep Space", "C", 55.0, 1.0, 1.0, 1.0, 0.0)) == {0}
    loud = shipped_frames("Deep Space", "C", 55.0, 1.0, 1.0, 1.0, 1.0, tmp_path / "l")
    assert set(loud["left"]) != {0}


def test_a_sample_never_leaves_the_range_a_whole_number_holds(tmp_path):
    """A sample ran past what a two-byte whole number can carry."""
    old = shipped_frames("Solar Wind", "F#", 220, 2.0, 3.0, 1.0, 1.0, tmp_path / "x")
    assert all(-surface.FULL_SCALE <= v <= surface.FULL_SCALE for v in old["left"])
    assert all(
        -surface.FULL_SCALE <= v <= surface.FULL_SCALE
        for v in surface_frames("Solar Wind", "F#", 220, 2.0, 3.0, 1.0, 1.0)
    )


def test_the_loop_join_is_the_length_the_surface_reports():
    """The loop join covers a different number of frames on the two sides."""
    assert surface.crossfade_frames() == int(surface.SAMPLE_RATE_HZ * 2.0)
    assert surface.crossfade_frames() == 88200
    assert surface.frame_total(SHORT_DURATION_S) < surface.crossfade_frames()


def test_a_sample_past_the_loop_join_is_not_mixed():
    """A sample past the join was still blended with the tail."""
    join = surface.crossfade_frames()
    plain = surface.unblended_sample(
        "Deep Space", join, 30.0, "C", 55.0, 1.0, 1.0, 1.0, 0.8
    )
    assert (
        surface.sample_value("Deep Space", join, 30.0, "C", 55.0, 1.0, 1.0, 1.0, 0.8)
        == plain
    )
    inside = surface.unblended_sample(
        "Deep Space", 20000, 30.0, "C", 55.0, 1.0, 1.0, 1.0, 0.8
    )
    mixed = surface.sample_value(
        "Deep Space", 20000, 30.0, "C", 55.0, 1.0, 1.0, 1.0, 0.8
    )
    assert mixed != inside


# ---------------------------------------------------------------------
# The file name the generator writes, held as text and never joined
# ---------------------------------------------------------------------

NAME_CASES = [
    (preset, key) for preset in EXPECTED_PRESET_NAMES for key in EXPECTED_KEY_NAMES
]


@pytest.mark.parametrize("preset,key", NAME_CASES)
def test_the_file_name_matches_the_shipped_one(preset, key):
    """The surface names a different file than the generator writes."""
    safe = preset.replace(" ", "_").replace("#", "s")
    assert surface.wav_file_name(preset, key) == "qat_%s_%s.wav" % (safe, key)


def test_the_generator_writes_the_name_the_surface_reports(tmp_path):
    """The surface names a file the generator does not write.

    Driven against the real generator, whose own file name is read off
    disk rather than typed here.
    """
    for preset, key in (
        ("Deep Space", "C"),
        ("White Noise Pad", "A#"),
        ("Meditation Bell", "F#"),
    ):
        written = shipped_frames(
            preset, key, 55.0, 1.0, 1.0, 0.3, 0.8, tmp_path / preset
        )
        assert written["name"] == surface.wav_file_name(preset, key)


def test_a_key_carrying_a_sharp_is_written_into_the_name_unchanged(tmp_path):
    """The key's sharp was taken out of the name on one side only.

    The shipped generator takes the sharp out of the PRESET name, which
    no preset carries, and writes the KEY in as it arrives. The surface
    does the same, so the two agree.
    """
    written = shipped_frames(
        "Deep Space", "C#", 55.0, 1.0, 1.0, 0.3, 0.8, tmp_path / "sharp"
    )
    assert written["name"] == "qat_Deep_Space_C#.wav"
    assert surface.wav_file_name("Deep Space", "C#") == written["name"]
    assert "#" in written["name"]
    assert all("#" not in name for name in EXPECTED_PRESET_NAMES)


def test_the_surface_names_the_directory_and_joins_nothing():
    """The surface reached the host's temporary directory."""
    assert surface.WAV_DIRECTORY_SOURCE == "tempfile.gettempdir()"
    assert os.sep not in surface.wav_file_name("Deep Space", "C")
    assert "/" not in surface.wav_file_name("Deep Space", "C")
    payload = surface.build_view_model("Deep Space", "C")
    assert payload["wav_directory_source"] == surface.WAV_DIRECTORY_SOURCE
    written = json.dumps(payload, default=repr)
    here = tempfile.gettempdir()
    # A backslash is doubled inside JSON, so the plain path never
    # matches on a Windows host and a check for it alone cannot fail.
    escaped = json.dumps(here)[1:-1]
    assert here not in written, here
    assert escaped not in written, escaped
    assert escaped in json.dumps(
        {"planted": here}
    ), "the reader cannot see a temporary path even when one is there"


@pytest.mark.parametrize("value", NON_STRING_NAMES)
def test_a_preset_name_that_is_not_text_refuses_the_same_way(value):
    """A name that is not text named a file instead of refusing."""
    old = outcome(lambda v: v.replace(" ", "_").replace("#", "s"), value)
    new = outcome(surface.safe_preset_name, value)
    assert new == old, (value, old, new)


# ---------------------------------------------------------------------
# The steps, driven through both sides in one run
# ---------------------------------------------------------------------

# One sequence is one named run of screen actions. Both sides are driven
# from this table and from nothing else, so neither can be given a
# starting value the other did not get.
SEQUENCES = {
    "nothing_at_all": [],
    "one_layer": [
        ("select_preset", (0, "Deep Space")),
        ("generate_all", ()),
    ],
    "every_layer": [
        ("select_preset", (0, "Deep Space")),
        ("select_preset", (1, "Theta Waves")),
        ("select_preset", (2, "Crystal Cave")),
        ("select_preset", (3, "Ocean Floor")),
        ("generate_all", ()),
    ],
    "layer_then_off_again": [
        ("select_preset", (0, "Solar Wind")),
        ("generate_all", ()),
        ("select_preset", (0, "")),
        ("generate_all", ()),
    ],
    "effects_moved": [
        ("set_detune", (0,)),
        ("set_lfo", (300,)),
        ("set_richness", (100,)),
        ("select_preset", (1, "Quantum Field")),
        ("generate_all", ()),
    ],
    "effects_out_of_range": [
        ("set_detune", (500,)),
        ("set_lfo", (-500,)),
        ("set_richness", (101,)),
        ("select_preset", (0, "Deep Space")),
        ("generate_all", ()),
    ],
    "key_chosen_then_shifted": [
        ("select_preset", (0, "Deep Space")),
        ("select_key", ("A#",)),
        ("generate_all", ()),
        ("key_up", ()),
    ],
    "key_wraps_past_the_last": [
        ("select_preset", (0, "Deep Space")),
        ("select_key", ("B",)),
        ("key_up", ()),
    ],
    "unknown_key_chosen": [
        ("select_preset", (0, "Deep Space")),
        ("select_key", ("H",)),
        ("generate_all", ()),
    ],
    "unknown_base_chosen": [
        ("select_base", ("999Hz",)),
        ("select_preset", (0, "Deep Space")),
        ("generate_all", ()),
    ],
    "base_chosen": [
        ("select_base", ("220Hz",)),
        ("select_preset", (0, "Deep Space")),
        ("generate_all", ()),
    ],
    "unknown_preset_chosen": [
        ("select_preset", (0, "no such preset")),
        ("generate_all", ()),
    ],
    "generated_then_stopped": [
        ("select_preset", (0, "Deep Space")),
        ("select_preset", (2, "Solar Wind")),
        ("generate_all", ()),
        ("stop_all", ()),
    ],
    "layer_error_after_generate": [
        ("select_preset", (0, "Deep Space")),
        ("select_preset", (1, "Theta Waves")),
        ("generate_all", ()),
        ("layer_error", (0,)),
    ],
    "layer_volumes_moved": [
        ("set_layer_volume", (0, 0)),
        ("set_layer_volume", (1, 100)),
        ("set_layer_volume", (2, 7)),
        ("set_layer_volume", (3, 99)),
    ],
    "layer_volume_out_of_range": [
        ("set_layer_volume", (0, 500)),
        ("set_layer_volume", (1, -500)),
        ("set_layer_volume", (2, 1.5)),
        ("set_layer_volume", (3, True)),
    ],
    "music_added_and_played": [
        ("add_files", (["/music/one.mp3", "/music/two.wav"],)),
        ("play_index", (0,)),
        ("next_track", ()),
        ("toggle_music", ()),
        ("toggle_music", ()),
        ("stop_music", ()),
    ],
    "music_wraps_at_the_end": [
        ("add_files", (["/music/one.mp3", "/music/two.wav"],)),
        ("play_index", (1,)),
        ("next_track", ()),
    ],
    "music_ended_moves_on": [
        ("add_files", (["/music/one.mp3", "/music/two.wav"],)),
        ("play_index", (0,)),
        ("music_ended", ()),
    ],
    "music_played_past_the_end": [
        ("add_files", (["/music/one.mp3"],)),
        ("play_index", (9,)),
    ],
    "music_toggled_with_no_files": [
        ("toggle_music", ()),
        ("next_track", ()),
    ],
    "music_volume_moved": [
        ("set_music_volume", (0,)),
        ("set_music_volume", (100,)),
        ("set_music_volume", (33,)),
    ],
    "unicode_file": [
        ("add_files", (["/music/Δ→⚡.ogg"],)),
        ("play_index", (0,)),
    ],
    "long_file_name": [
        ("add_files", (["/music/" + "X" * 200 + ".flac"],)),
        ("play_index", (0,)),
    ],
    "markup_file_name": [
        ("add_files", (["/music/<b>three</b>.m4a"],)),
        ("play_index", (0,)),
    ],
    "apostrophe_file_name": [
        ("add_files", (["/music/it's here.mp3"],)),
        ("play_index", (0,)),
    ],
    "newline_file_name": [
        ("add_files", (["/music/four\nfive.mp3"],)),
        ("play_index", (0,)),
    ],
    "empty_file_name": [
        ("add_files", ([""],)),
        ("play_index", (0,)),
    ],
    "waveform_moves_after_a_layer_plays": [
        ("select_preset", (0, "Deep Space")),
        ("generate_all", ()),
        ("animate", (0.033,)),
        ("animate", (0.033,)),
    ],
    "waveform_stays_still_while_idle": [
        ("animate", (0.033,)),
        ("animate", (0.033,)),
    ],
    "layer_restarts_at_the_end_of_its_tone": [
        ("select_preset", (0, "Deep Space")),
        ("generate_all", ()),
        ("layer_ended", (0,)),
    ],
}

# Sequences that stop part way. Each names where it stops and why.
REFUSING_SEQUENCES = {
    "layer_past_the_last": (
        [
            ("select_preset", (0, "Deep Space")),
            ("select_preset", (9, "Theta Waves")),
            ("generate_all", ()),
        ],
        1,
        "select_preset",
        "IndexError",
    ),
    "layer_named_by_text": (
        [
            ("set_layer_volume", (0, 70)),
            ("set_layer_volume", ("x", 70)),
        ],
        1,
        "set_layer_volume",
        "TypeError",
    ),
    "volume_as_text": (
        [
            ("set_layer_volume", (0, 70)),
            ("set_layer_volume", (1, "x")),
        ],
        1,
        "set_layer_volume",
        "TypeError",
    ),
    "volume_as_nothing": (
        [("set_layer_volume", (0, None))],
        0,
        "set_layer_volume",
        "TypeError",
    ),
    "detune_infinite": (
        [("set_detune", (math.inf,))],
        0,
        "set_detune",
        "OverflowError",
    ),
    "detune_minus_infinite": (
        [("set_detune", (-math.inf,))],
        0,
        "set_detune",
        "OverflowError",
    ),
    "lfo_not_a_number": (
        [("set_lfo", (math.nan,))],
        0,
        "set_lfo",
        "OverflowError",
    ),
    "richness_past_a_whole_number": (
        [("set_richness", (2**31,))],
        0,
        "set_richness",
        "OverflowError",
    ),
    "richness_as_bytes": (
        [("set_richness", (b"50",))],
        0,
        "set_richness",
        "TypeError",
    ),
    "files_that_are_not_a_list": (
        [("add_files", (5,))],
        0,
        "add_files",
        "TypeError",
    ),
    "played_by_text": (
        [
            ("add_files", (["/music/one.mp3"],)),
            ("play_index", ("x",)),
        ],
        1,
        "play_index",
        "TypeError",
    ),
    "animated_by_text_after_a_layer_plays": (
        [
            ("select_preset", (0, "Deep Space")),
            ("generate_all", ()),
            ("animate", ("x",)),
        ],
        2,
        "animate",
        "TypeError",
    ),
    "a_step_that_does_not_exist": (
        [
            ("select_preset", (0, "Deep Space")),
            ("no_such_step", ()),
        ],
        1,
        "no_such_step",
        "UnknownStep",
    ),
    "music_volume_by_text": (
        [("set_music_volume", ("x",))],
        0,
        "set_music_volume",
        "TypeError",
    ),
}


@pytest.mark.parametrize("case", sorted(SEQUENCES))
@pytest.mark.parametrize("media", ALL_MEDIA_STATES)
def test_both_sides_end_one_sequence_in_the_same_state(case, media, tmp_path):
    """The two sides ended one run of screen actions differently."""
    steps = SEQUENCES[case]
    old = run_shipped(steps, media, tmp_path / "old")
    new = run_surface(steps, media)
    found = differences(old["state"], new["state"])
    assert found == [], (case, media, found)
    assert old["stopped_at_index"] == new["stopped_at_index"], (case, media)
    assert old["stopped_at_step"] == new["stopped_at_step"], (case, media)
    assert old["refusal"] == new["refusal"], (case, media)


@pytest.mark.parametrize("case", sorted(SEQUENCES))
@pytest.mark.parametrize("media", ALL_MEDIA_STATES)
def test_both_sides_pass_through_the_same_state_at_every_step(case, media, tmp_path):
    """The two sides differed at a step but agreed at the end."""
    steps = SEQUENCES[case]
    old = run_shipped(steps, media, tmp_path / "old")
    new = run_surface(steps, media)
    assert len(old["steps_done"]) == len(new["steps_done"]), (case, media)
    for done_old, done_new in zip(old["steps_done"], new["steps_done"]):
        assert done_old["index"] == done_new["index"], case
        assert done_old["step"] == done_new["step"], case
        found = differences(done_old["state"], done_new["state"])
        assert found == [], (case, media, done_old["index"], done_old["step"], found)


@pytest.mark.parametrize("case", sorted(REFUSING_SEQUENCES))
def test_a_sequence_that_refuses_stops_at_the_same_step(case, tmp_path):
    """A sequence stopped at a different step, or for a different reason."""
    steps, index, name, refusal = REFUSING_SEQUENCES[case]
    old = run_shipped(steps, MEDIA_READY, tmp_path / "old")
    new = run_surface(steps, MEDIA_READY)
    assert old["stopped_at_index"] == index, (case, old)
    assert old["stopped_at_step"] == name, (case, old)
    assert old["refusal"] == refusal, (case, old)
    assert new["stopped_at_index"] == index, (case, new)
    assert new["stopped_at_step"] == name, (case, new)
    assert new["refusal"] == refusal, (case, new)
    assert len(old["steps_done"]) == index
    assert len(new["steps_done"]) == index


@pytest.mark.parametrize("case", sorted(REFUSING_SEQUENCES))
def test_a_sequence_that_refuses_leaves_both_sides_alike(case, tmp_path):
    """A refusal part way left the two sides holding different values."""
    steps, _, _, _ = REFUSING_SEQUENCES[case]
    old = run_shipped(steps, MEDIA_READY, tmp_path / "old")
    new = run_surface(steps, MEDIA_READY)
    found = differences(old["state"], new["state"])
    assert found == [], (case, found)


def test_the_music_controls_are_absent_without_the_sound_library(tmp_path):
    """The music panel built controls it cannot have, or refused wrongly."""
    steps = [("add_files", (["/music/one.mp3", "/music/two.wav"],))]
    old = run_shipped(steps, MEDIA_LIBRARY_MISSING, tmp_path / "old")
    new = run_surface(steps, MEDIA_LIBRARY_MISSING)
    assert old["refusal"] == "AttributeError", old
    assert new["refusal"] == old["refusal"], (old, new)
    assert old["state"]["music_files"] == ["/music/one.mp3"], old["state"]
    assert differences(old["state"], new["state"]) == []
    ready = run_shipped(steps, MEDIA_READY, tmp_path / "ready")
    assert ready["refusal"] == "", ready
    assert ready["state"]["music_files"] == ["/music/one.mp3", "/music/two.wav"]


@pytest.mark.parametrize("step", ["stop_music", "set_music_volume"])
def test_a_missing_music_control_refuses_the_same_way(step, tmp_path):
    """A control the panel never built answered instead of refusing."""
    steps = [(step, (50,) if step == "set_music_volume" else ())]
    old = run_shipped(steps, MEDIA_LIBRARY_MISSING, tmp_path / "old")
    new = run_surface(steps, MEDIA_LIBRARY_MISSING)
    assert old["refusal"] == "AttributeError", (step, old)
    assert new["refusal"] == old["refusal"], (step, old, new)
    ready = run_shipped(steps, MEDIA_READY, tmp_path / "ready")
    assert ready["refusal"] == "", (step, ready)


def test_a_device_that_refuses_leaves_the_controls_and_plays_nothing(tmp_path):
    """A refused device took the music controls away, or played anyway."""
    steps = [
        ("add_files", (["/music/one.mp3"],)),
        ("play_index", (0,)),
        ("select_preset", (0, "Deep Space")),
        ("generate_all", ()),
    ]
    old = run_shipped(steps, MEDIA_DEVICE_REFUSED, tmp_path / "old")
    new = run_surface(steps, MEDIA_DEVICE_REFUSED)
    assert old["refusal"] == "", old
    assert differences(old["state"], new["state"]) == []
    assert old["state"]["music_playing"] is False
    assert old["state"]["music_caption"] == "Nothing playing"
    assert old["state"]["layer_playing"] == [False] * LAYER_TOTAL
    assert "no WAV" in old["state"]["drone_status"]
    assert "Media: " not in old["state"]["drone_status"]


def test_the_status_names_the_library_and_not_the_device(tmp_path):
    """The status line read the device where it reads the library.

    A refused device still leaves the library loaded, so the status says
    the media is there. Only a missing library makes it say otherwise,
    and then the error wording wins.
    """
    steps = [("select_preset", (0, "Deep Space")), ("generate_all", ())]
    ready = run_shipped(steps, MEDIA_READY, tmp_path / "a")
    assert "Media: OK" in ready["state"]["drone_status"]
    assert run_surface(steps, MEDIA_READY)["state"]["drone_status"] == (
        ready["state"]["drone_status"]
    )
    for media in (MEDIA_DEVICE_REFUSED, MEDIA_LIBRARY_MISSING):
        run = run_shipped(steps, media, tmp_path / media)
        assert run["state"]["drone_status"].startswith("1 layer(s) "), run
        assert "ERRORS" in run["state"]["drone_status"], run
        assert run_surface(steps, media)["state"]["drone_status"] == (
            run["state"]["drone_status"]
        )


def test_the_transient_status_is_the_one_the_surface_names(tmp_path):
    """The panel writes a different line while it is building."""
    with side_world(MEDIA_READY, tmp_path / "old"):
        tab = ShippedTab()
        try:
            tab.step("select_preset", (0, "Deep Space"))
            tab.step("generate_all", ())
            assert tab.generating_texts == [
                surface.GENERATING_TEXT
            ], tab.generating_texts
            assert tab.drone._st.text() != surface.GENERATING_TEXT
        finally:
            tab.close()


def test_the_key_shift_names_the_key_it_is_moving_to(tmp_path):
    """The shift line names a different key than the one chosen."""
    with side_world(MEDIA_READY, tmp_path / "old"):
        tab = ShippedTab()
        try:
            tab.step("select_key", ("A#",))
            tab.step("key_up", ())
            assert tab.generating_texts == [
                surface.SHIFTING_FORMAT.format("B"),
                surface.GENERATING_TEXT,
            ], tab.generating_texts
        finally:
            tab.close()


@pytest.mark.parametrize("case", sorted(SLIDER_CASES))
def test_a_slider_takes_or_refuses_the_same_value_on_both_sides(case, tmp_path):
    """A slider setting was taken on one side and refused on the other."""
    value = SLIDER_CASES[case]
    with side_world(MEDIA_READY, tmp_path / "old"):
        tab = ShippedTab()
        try:
            old = outcome(
                lambda v: (tab.drone._det.setValue(v), tab.drone._det.value())[1],
                value,
            )
        finally:
            tab.close()
    new = outcome(surface.slider_value, value, 0, 100)
    assert new == old, (case, value, old, new)


@pytest.mark.parametrize("case", sorted(FILE_CASES))
def test_a_music_file_is_captioned_the_same_way_on_both_sides(case):
    """The caption named a different part of the path on the two sides."""
    path = FILE_CASES[case]
    assert surface.now_playing_text(path) == "Playing: " + os.path.basename(path)


def test_a_caption_for_a_path_that_is_not_text_refuses(tmp_path):
    """A path that is not text was captioned instead of refusing."""
    for value in (5, None, [], {}):
        old = outcome(lambda v: "Playing: %s" % os.path.basename(v), value)
        new = outcome(surface.now_playing_text, value)
        assert new == old, (value, old, new)
        assert new["did"] == REFUSAL_TYPE, value


# ---------------------------------------------------------------------
# One whole answer, by hash
# ---------------------------------------------------------------------

HASH_SAMPLES = (
    "one_layer",
    "every_layer",
    "music_added_and_played",
    "effects_out_of_range",
    "generated_then_stopped",
)


@pytest.mark.parametrize("case", HASH_SAMPLES)
def test_the_two_sides_hash_the_same(case, tmp_path):
    """The two whole answers hash apart."""
    steps = SEQUENCES[case]
    old = digest(run_shipped(steps, MEDIA_READY, tmp_path / "old")["state"])
    new = digest(run_surface(steps, MEDIA_READY)["state"])
    assert new == old, (case, old, new)


def test_the_sample_hashes_are_reported(tmp_path):
    """A sample hash is missing or is not a hash."""
    samples = {}
    for case in HASH_SAMPLES:
        state = run_shipped(SEQUENCES[case], MEDIA_READY, tmp_path / case)["state"]
        samples[case] = digest(state)
    for name, value in samples.items():
        assert len(value) == 64, (name, value)
        assert set(value) <= set("0123456789abcdef"), (name, value)
    assert len(set(samples.values())) == len(samples), samples
    for case, value in samples.items():
        assert digest(run_surface(SEQUENCES[case], MEDIA_READY)["state"]) == value


def test_two_different_real_runs_hash_apart(tmp_path):
    """The hash gives one value for every run, so it tells nothing apart.

    Two real sequences, one driven through each side, and then the same
    pair the other way about. A pass proves the hash reports a
    difference.
    """
    old_one = digest(
        run_shipped(SEQUENCES["one_layer"], MEDIA_READY, tmp_path / "a")["state"]
    )
    new_every = digest(run_surface(SEQUENCES["every_layer"], MEDIA_READY)["state"])
    assert old_one != new_every
    old_every = digest(
        run_shipped(SEQUENCES["every_layer"], MEDIA_READY, tmp_path / "b")["state"]
    )
    new_one = digest(run_surface(SEQUENCES["one_layer"], MEDIA_READY)["state"])
    assert old_every != new_one
    assert old_one == new_one
    assert old_every == new_every


def test_the_same_run_hashes_the_same_twice(tmp_path):
    """The hash moves between two runs over one input."""
    first = digest(run_surface(SEQUENCES["every_layer"], MEDIA_READY)["state"])
    second = digest(run_surface(SEQUENCES["every_layer"], MEDIA_READY)["state"])
    assert first == second
    old_first = digest(
        run_shipped(SEQUENCES["one_layer"], MEDIA_READY, tmp_path / "a")["state"]
    )
    old_second = digest(
        run_shipped(SEQUENCES["one_layer"], MEDIA_READY, tmp_path / "b")["state"]
    )
    assert old_first == old_second


def test_the_difference_reader_names_what_moved(tmp_path):
    """The difference reader reports nothing whatever it is given."""
    state = run_surface(SEQUENCES["one_layer"], MEDIA_READY)["state"]
    moved = dict(state)
    moved["drone_status"] = "something else"
    found = differences(state, moved)
    assert found == [
        "/drone_status: %r against %r" % (state["drone_status"], moved["drone_status"])
    ], found
    listed = dict(state)
    listed["layer_playing"] = [True, True, False, False]
    named = differences(state, listed)
    assert len(named) == 1, named
    assert "layer_playing[1]" in named[0], named
    assert differences(state, state) == []


# ---------------------------------------------------------------------
# What the shipped file has, and where each item went
# ---------------------------------------------------------------------

SCREEN_ROOTS = ("PySide6.QtWidgets",)

SURFACE_FUNCTIONS = (
    "key_multiplier",
    "preset_intervals",
    "has_preset",
    "has_key",
    "whole_number",
    "slider_value",
    "has_player",
    "has_music_controls",
    "missing_control",
    "chosen_preset",
    "key_index_for",
    "base_index_for",
    "layer_volume_pct",
    "layer_label",
    "volume_label",
    "output_volume",
    "effect_values",
    "safe_preset_name",
    "wav_file_name",
    "now_playing_text",
    "frame_total",
    "crossfade_frames",
    "unblended_sample",
    "sample_value",
    "next_key_index",
    "drone_status",
    "drone_error_status",
    "initial_state",
    "copied_state",
    "current_key",
    "current_base_freq",
    "active_layer_total",
    "generated",
    "key_text",
    "reported_to_waveform",
    "played",
    "toggled",
    "layer_index",
    "layer_step",
    "drone_step",
    "music_step",
    "waveform_step",
    "stepped",
    "apply_step",
    "run_steps",
    "requested_name",
    "preset_answer",
    "key_answer",
    "build_view_model",
    "view_model",
)

# Every item the shipped file holds, and what stands for it here. The
# file write and the device calls have no counterpart: a view model
# writes nothing and opens nothing.
COUNTERPARTS = {
    "KEY_MULT": "KEY_MULTIPLIERS",
    "ToneGenerator.SR": "SAMPLE_RATE_HZ",
    "ToneGenerator.PRESETS": "PRESETS",
    "ToneGenerator.generate_wav": "sample_value",
    "WaveformWidget.set_state": "waveform_step",
    "WaveformWidget.animate": "waveform_step",
    "WaveformWidget.paintEvent": "LAYER_TRACE_COLOURS",
    "DroneLayer._on_vol": "layer_step",
    "DroneLayer.gen_play": "generated",
    "DroneLayer.stop": "drone_step",
    "DroneLayer.is_active": "active_layer_total",
    "DroneLayer._on_end": "layer_step",
    "DroneLayer._on_error": "layer_step",
    "DroneLayer._on_state": "layer_step",
    "MusicPlayerPanel._add": "music_step",
    "MusicPlayerPanel._tog": "toggled",
    "MusicPlayerPanel._pi": "played",
    "MusicPlayerPanel._stp": "music_step",
    "MusicPlayerPanel._nxt": "music_step",
    "MusicPlayerPanel._sv": "output_volume",
    "MusicPlayerPanel._oe": "music_step",
    "DroneEnginePanel._fx": "effect_values",
    "DroneEnginePanel._gen_all": "generated",
    "DroneEnginePanel._stop_all": "drone_step",
    "DroneEnginePanel._key_up": "next_key_index",
    "DroneEnginePanel._es": "active_layer_total",
    "_sc": "run_steps",
}

# The three things the shipped file does that a view model does not, each
# with the test that covers what is left of it.
NO_COUNTERPART = {
    "writing the wav file": "test_the_generator_writes_the_name_the_surface_reports",
    "opening the audio device": "test_a_device_that_refuses_leaves_the_controls_and_plays_nothing",
    "opening the file chooser": "test_the_file_chooser_is_named_and_never_opened",
}


def parsed(path):
    """One file's syntax tree. Prose cannot be read from a syntax tree."""
    return ast.parse(path.read_text(encoding="utf-8"))


def call_name(node):
    """The last name of a call's target, however it was reached."""
    target = node.func
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return ""


def dotted_call(node):
    """A call's whole target, written back out from the parsed file.

    A receiver that is itself a call, such as ``get_event_bus().emit``,
    is part of the target. Walking only the attribute chain drops it and
    reports the bare method name, which is how a bus counter reads two
    of five sites.
    """
    return ast.unparse(node.func)


def classes_in(path):
    """Every class a file declares, including one declared inside a method."""
    return [
        node.name for node in ast.walk(parsed(path)) if isinstance(node, ast.ClassDef)
    ]


def methods_in(path):
    """Every method a file declares, on every class, at any depth.

    A read-only value and a factory are declared with `def` and are
    counted. A signal is an assignment and is not.
    """
    found = []
    for owner in ast.walk(parsed(path)):
        if not isinstance(owner, ast.ClassDef):
            continue
        for member in owner.body:
            if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found.append("%s.%s" % (owner.name, member.name))
    return found


def module_functions_in(path):
    """Every function a file declares outside any class."""
    return [
        node.name
        for node in parsed(path).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def signals_in(path):
    """Every signal a file declares, by the call that builds it."""
    found = []
    for node in ast.walk(parsed(path)):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        if call_name(node.value) not in ("Signal", "pyqtSignal"):
            continue
        found.extend(
            target.id for target in node.targets if isinstance(target, ast.Name)
        )
    return found


def connects_in(path):
    """Every wiring a file makes, counted from the parsed file."""
    return [
        node.lineno
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call) and call_name(node) == "connect"
    ]


def timers_built_in(path):
    """Every timer object a file builds."""
    return [
        node.lineno
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call) and call_name(node) == "QTimer"
    ]


def timers_single_shot_in(path):
    """Every timer a file runs without building one.

    `QTimer.singleShot` starts a timer and hands back nothing, so a
    counter that only looks for a construction reports none.
    """
    return [
        node.lineno
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call) and dotted_call(node).endswith("singleShot")
    ]


def threads_in(path):
    """Every worker thread a file starts."""
    return [
        node.lineno
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call)
        and call_name(node) in ("QThread", "Thread", "QRunnable")
    ]


def bus_subscribes_in(path):
    """Every event-bus topic a file listens to."""
    return [
        node.lineno
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call) and call_name(node) == "subscribe"
    ]


def bus_emits_in(path):
    """Every event-bus message a file sends.

    A signal is emitted through the object that declares it, so the
    receiver decides which of the two this is.
    """
    return [
        node.lineno
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call)
        and call_name(node) == "emit"
        and "bus" in dotted_call(node).lower()
    ]


def signal_emits_in(path):
    """Every signal a file sends."""
    return [
        node.lineno
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call)
        and call_name(node) == "emit"
        and "bus" not in dotted_call(node).lower()
    ]


def screen_elements_in(module, path):
    """Every screen element a file builds, resolved against the real class.

    A name is looked up on the module and asked whether it is a widget,
    so a project's own widget counts and a layout does not. Counting a
    fixed list of names instead reports two where the file builds three.
    """
    from PySide6.QtWidgets import QWidget

    found = []
    for node in ast.walk(parsed(path)):
        if not isinstance(node, ast.Call):
            continue
        parts = dotted_call(node).split(".")
        if not parts or not parts[0]:
            continue
        target = getattr(module, parts[0], None)
        for step in parts[1:]:
            target = getattr(target, step, None)
        if isinstance(target, type) and issubclass(target, QWidget):
            found.append((node.lineno, ".".join(parts)))
    return found


def test_the_class_counter_reports_every_class_the_shipped_file_declares():
    """A class appeared or disappeared on the shipped side."""
    found = classes_in(SHIPPED_PATH)
    assert len(found) == SHIPPED_CLASS_TOTAL, found
    assert found.count("AudioSuiteTab") == 2, found
    assert len(set(found)) == SHIPPED_REACHABLE_CLASS_TOTAL, found
    assert set(found) == {
        "ToneGenerator",
        "WaveformWidget",
        "DroneLayer",
        "MusicPlayerPanel",
        "DroneEnginePanel",
        "AudioSuiteTab",
    }, found


def test_the_class_counter_finds_a_class_declared_inside_a_method():
    """The class counter reads the top of a file only, so a nested one hides."""
    found = classes_in(NESTED_CLASS_NEIGHBOUR_PATH)
    assert NESTED_CLASS_NAME in found, found
    top_level = [
        node.name
        for node in parsed(NESTED_CLASS_NEIGHBOUR_PATH).body
        if isinstance(node, ast.ClassDef)
    ]
    assert NESTED_CLASS_NAME not in top_level, top_level


def test_the_surface_declares_one_class_and_it_is_a_refusal():
    """The surface grew a class the shipped file has no counterpart for."""
    assert classes_in(SURFACE_PATH) == ["UnknownStep"], classes_in(SURFACE_PATH)
    assert issubclass(surface.UnknownStep, LookupError)


def test_the_method_counter_reports_every_method_the_shipped_file_declares():
    """A method appeared or disappeared on the shipped side."""
    found = methods_in(SHIPPED_PATH)
    assert len(found) == SHIPPED_METHOD_TOTAL, found
    assert "DroneLayer.is_active" in found, found
    assert "ToneGenerator.generate_wav" in found, found
    assert found.count("AudioSuiteTab.__init__") == 2, found


def test_the_method_counter_leaves_a_signal_out():
    """The counter reported a signal as a method.

    A signal is callable and is not a method. The counter is pointed at
    a neighbouring class that carries one and must report the methods
    while leaving the signal out.
    """
    from src.gui import launcher

    signal = vars(launcher.ModeCard)[EXCLUDED_SIGNAL_NAME]
    assert callable(signal), "the signal is not callable, so nothing is excluded"
    assert not inspect.isfunction(signal)
    found = methods_in(SIGNAL_NEIGHBOUR_PATH)
    assert "ModeCard." + EXCLUDED_SIGNAL_NAME not in found, found
    assert "ModeCard.mousePressEvent" in found, found


@pytest.mark.parametrize("name", READ_ONLY_MEMBERS)
def test_the_method_counter_finds_a_read_only_value_and_a_factory(name):
    """The counter skipped a member that carries a decorator."""
    found = methods_in(READ_ONLY_NEIGHBOUR_PATH)
    assert any(entry.endswith("." + name) for entry in found), (name, len(found))


def test_the_module_function_counter_reports_the_one_helper():
    """A helper outside a class appeared or disappeared."""
    found = module_functions_in(SHIPPED_PATH)
    assert found == ["_sc"], found
    assert len(found) == SHIPPED_MODULE_FUNCTION_TOTAL


def test_the_signal_counter_reports_both_signals():
    """A signal appeared or disappeared on the shipped side."""
    found = signals_in(SHIPPED_PATH)
    assert sorted(found) == ["drone_state", "state_changed"], found
    assert len(found) == SHIPPED_SIGNAL_TOTAL
    assert list(surface.SIGNALS) == ["state_changed", "drone_state"]


def test_the_signal_counter_can_see_a_signal():
    """The signal counter reported none because it can never report one."""
    found = signals_in(SIGNAL_NEIGHBOUR_PATH)
    assert len(found) == SIGNAL_NEIGHBOUR_SIGNALS, found


def test_the_connect_sites_match_the_actions():
    """A wiring on the shipped side has no action named for it."""
    found = connects_in(SHIPPED_PATH)
    assert len(found) == SHIPPED_CONNECT_TOTAL, found
    assert len(surface.ACTIONS) == len(found), sorted(surface.ACTIONS)
    assert connects_in(SURFACE_PATH) == []


def test_every_action_carries_a_description():
    """An action was named with nothing said about it."""
    for name, said in surface.ACTIONS.items():
        assert said.strip(), name
        assert said == said.strip(), name


def test_the_connect_counter_can_see_a_wiring():
    """The wiring counter reported none because it can never report one."""
    assert len(connects_in(WIRED_NEIGHBOUR_PATH)) == WIRED_NEIGHBOUR_CONNECTS


def test_the_timer_counter_reports_one_built_and_none_run_without_building():
    """A timer appeared or disappeared on the shipped side."""
    built = timers_built_in(SHIPPED_PATH)
    single = timers_single_shot_in(SHIPPED_PATH)
    assert len(built) == SHIPPED_TIMER_BUILT_TOTAL, built
    assert len(single) == SHIPPED_TIMER_SINGLE_SHOT_TOTAL, single
    assert timers_built_in(SURFACE_PATH) == []
    assert timers_single_shot_in(SURFACE_PATH) == []
    assert surface.TIMERS == {"waveform_animation": 33}
    assert surface.TIMER_DELAYS_MS == (33,)


def test_the_timer_that_is_built_belongs_to_the_tab(tmp_path):
    """The one timer is owned by something else, or is not running.

    The timer is read off the live tab rather than from the file, so the
    owner is the real one.
    """
    with side_world(MEDIA_READY, tmp_path / "old"):
        tab = ShippedTab()
        try:
            assert tab.timer_was_active is True
            assert tab.tab._at.interval() == surface.TIMERS["waveform_animation"]
            assert tab.tab._at.parent() is tab.tab
            assert tab.tab._at.isActive() is False
        finally:
            tab.close()


def test_the_timer_counter_can_see_a_timer_and_tells_two_namesakes_apart():
    """The timer counter reported none because it can never report one.

    Two files share a name. One builds a timer and one does not, so a
    control named without its path proves nothing.
    """
    assert len(timers_built_in(TIMER_NEIGHBOUR_PATH)) == TIMER_NEIGHBOUR_TIMERS
    assert len(timers_built_in(TIMER_NAMESAKE_PATH)) == TIMER_NAMESAKE_TIMERS
    assert TIMER_NEIGHBOUR_PATH.name == TIMER_NAMESAKE_PATH.name
    assert TIMER_NEIGHBOUR_PATH != TIMER_NAMESAKE_PATH


def test_the_single_shot_counter_can_see_a_timer_run_without_building_one():
    """The counter reported none because it cannot see the other form."""
    found = timers_single_shot_in(READ_ONLY_NEIGHBOUR_PATH)
    assert len(found) == SINGLE_SHOT_NEIGHBOUR_TOTAL, found
    assert len(timers_built_in(READ_ONLY_NEIGHBOUR_PATH)) > 0


def test_no_thread_is_started_on_either_side():
    """A worker thread appeared that nothing waits for."""
    assert threads_in(SHIPPED_PATH) == []
    assert threads_in(SURFACE_PATH) == []
    assert surface.THREAD_TOTAL == SHIPPED_THREAD_TOTAL


def test_the_thread_counter_can_see_a_thread():
    """The thread counter reported none because it can never report one."""
    written = REPO_ROOT / "src/gui/main_tabs/audio_suite_surface.py"
    made_up = ast.parse("from PySide6.QtCore import QThread\nworker = QThread()\n")
    found = [
        node.lineno
        for node in ast.walk(made_up)
        if isinstance(node, ast.Call) and call_name(node) == "QThread"
    ]
    assert found == [2], found
    assert threads_in(written) == []


def test_the_bus_counters_report_none_in_both_directions():
    """The audio tab reached the event bus, in one direction or the other."""
    assert bus_subscribes_in(SHIPPED_PATH) == []
    assert bus_emits_in(SHIPPED_PATH) == []
    assert bus_subscribes_in(SURFACE_PATH) == []
    assert bus_emits_in(SURFACE_PATH) == []
    assert surface.BUS_TOPICS == ()


def test_the_bus_counters_can_see_both_directions():
    """A bus counter reported none because it can never report one."""
    assert len(bus_subscribes_in(BUS_NEIGHBOUR_PATH)) == BUS_NEIGHBOUR_SUBSCRIBES
    assert len(bus_emits_in(BUS_NEIGHBOUR_PATH)) == BUS_NEIGHBOUR_EMITS


def test_the_signal_emit_counter_is_not_the_bus_counter():
    """The two emit counters read the same sites, so one of them is blind."""
    found = signal_emits_in(SHIPPED_PATH)
    assert len(found) == SHIPPED_SIGNAL_EMIT_TOTAL, found
    assert bus_emits_in(SHIPPED_PATH) == []
    assert len(signal_emits_in(BUS_NEIGHBOUR_PATH)) == 0
    assert len(bus_emits_in(BUS_NEIGHBOUR_PATH)) == BUS_NEIGHBOUR_EMITS


def test_the_screen_element_counter_reports_what_the_file_builds():
    """A screen element appeared or disappeared on the shipped side."""
    found = screen_elements_in(shipped, SHIPPED_PATH)
    assert len(found) == SHIPPED_SCREEN_ELEMENT_TOTAL, found
    names = [name for _, name in found]
    assert "DroneLayer" in names, names
    assert "QVBoxLayout" not in names, names
    assert screen_elements_in(surface, SURFACE_PATH) == []


def test_the_screen_element_counter_finds_a_widget_the_project_wrote():
    """The counter reads a fixed list of names, so a project widget hides.

    The control file builds two labels and one dot. A counter that knows
    only the platform's own names reports two.
    """
    from src.gui.widgets import dashboard_stat_card

    found = screen_elements_in(dashboard_stat_card, SCREEN_NEIGHBOUR_PATH)
    assert len(found) == SCREEN_NEIGHBOUR_ELEMENTS, found
    names = [name for _, name in found]
    assert names.count("PrivacyDot") == 1, names
    assert names.count("QLabel") == 2, names


def test_every_shipped_item_has_a_counterpart():
    """An item on the shipped side has nothing standing for it."""
    for old_name, new_name in COUNTERPARTS.items():
        owner = shipped
        for part in old_name.split("."):
            owner = getattr(owner, part, None)
            assert owner is not None, old_name
        assert hasattr(surface, new_name), (old_name, new_name)
    declared = set(methods_in(SHIPPED_PATH)) | set(module_functions_in(SHIPPED_PATH))
    named = set(COUNTERPARTS) | {
        "WaveformWidget.__init__",
        "DroneLayer.__init__",
        "MusicPlayerPanel.__init__",
        "DroneEnginePanel.__init__",
        "AudioSuiteTab.__init__",
    }
    unaccounted = sorted(name for name in declared if name not in named)
    assert unaccounted == [], unaccounted


def test_the_three_things_a_view_model_does_not_do_are_named_and_covered():
    """A device call or a file write was left with nothing said about it."""
    assert len(NO_COUNTERPART) == 3
    for covered_by in NO_COUNTERPART.values():
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by


def test_the_surface_functions_are_reachable_and_described():
    """A named helper is missing, or carries no description."""
    found = {
        name
        for name, value in vars(surface).items()
        if inspect.isfunction(value)
        and getattr(value, "__module__", "") == surface.__name__
    }
    assert found == set(SURFACE_FUNCTIONS), sorted(found ^ set(SURFACE_FUNCTIONS))
    for name in SURFACE_FUNCTIONS:
        member = getattr(surface, name)
        assert callable(member), name
        assert (member.__doc__ or "").strip(), name
    with pytest.raises(AttributeError):
        surface.no_such_helper()


def test_the_file_chooser_is_named_and_never_opened():
    """The surface reached a file chooser, or named a different filter."""
    assert surface.FILE_DIALOG_TITLE == "Music"
    assert surface.FILE_DIALOG_FILTER == "Audio (*.mp3 *.wav *.ogg *.flac *.m4a)"
    imported = set()
    for node in ast.walk(parsed(SURFACE_PATH)):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert imported == {"__future__", "math", "os", "typing"}, imported
    names = [name for _, name in screen_elements_in(shipped, SHIPPED_PATH)]
    assert "QFileDialog" not in names, names


# ---------------------------------------------------------------------
# The surface without Qt
# ---------------------------------------------------------------------


def test_the_surface_loads_no_qt_module():
    """The surface grew an import that pulls Qt into the backend."""
    imported = set()
    for node in ast.walk(parsed(SURFACE_PATH)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(name.startswith("PySide6") for name in imported), imported
    assert not any(name.startswith("shiboken") for name in imported), imported


def test_the_import_reader_can_see_a_qt_import():
    """The import reader reported none because it can never report one."""
    imported = {
        node.module or ""
        for node in ast.walk(parsed(SHIPPED_PATH))
        if isinstance(node, ast.ImportFrom)
    }
    assert any(name.startswith("PySide6") for name in imported), imported


def test_nothing_reaches_the_world_when_the_surface_is_imported():
    """The surface opened a file, a device or the clock as it loaded."""
    forbidden = {"gettempdir", "open", "getsize", "exists", "time", "now", "monotonic"}
    called = set()
    for node in ast.walk(parsed(SURFACE_PATH)):
        if isinstance(node, ast.Call):
            called.add(call_name(node))
    assert called & forbidden == set(), sorted(called & forbidden)
    top_level_calls = []
    for node in parsed(SURFACE_PATH).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call):
                top_level_calls.append(dotted_call(inner))
    assert top_level_calls != [], "the reader found no call at all to judge"
    assert set(top_level_calls) <= {"tuple", "dict", "list", "frozenset"}, sorted(
        set(top_level_calls)
    )


def test_neither_file_reads_the_clock():
    """A value on either side moves with the time of day."""
    for path in (SHIPPED_PATH, SURFACE_PATH):
        imported = set()
        for node in ast.walk(parsed(path)):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert "time" not in imported, (path.name, imported)
        assert "datetime" not in imported, (path.name, imported)
    called = {
        call_name(node)
        for path in (SHIPPED_PATH, SURFACE_PATH)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call)
    }
    assert "time" not in called, called
    assert "monotonic" not in called, called
    assert "now" not in called, called


def test_the_clock_reader_can_see_a_clock():
    """The clock reader reported none because it can never report one."""
    made_up = ast.parse("import time\nwhen = time.time()\n")
    imported = {
        alias.name
        for node in ast.walk(made_up)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "time" in imported
    called = {
        call_name(node) for node in ast.walk(made_up) if isinstance(node, ast.Call)
    }
    assert "time" in called


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

COUNT_CONNECTIONS = (
    "import socket\n"
    "_attempts = []\n"
    "_real_connect = socket.socket.connect\n"
    "def _counted(self, address, *rest):\n"
    "    _attempts.append(repr(address))\n"
    "    raise OSError('no network in this run')\n"
    "socket.socket.connect = _counted\n"
    "socket.create_connection = _counted\n"
)

BRIDGE_PROBE = (
    BLOCK_QT
    + COUNT_CONNECTIONS
    + (
        "import json\n"
        "from src.core import desktop_bridge\n"
        "registry = desktop_bridge.build_registry()\n"
        "frame = desktop_bridge.handle_line(json.dumps({'id': 1,\n"
        "    'method': 'audio_suite.state',\n"
        "    'params': {'preset': 'Crystal Cave', 'key': 'A#',\n"
        "               'steps': [['select_preset', [0, 'Deep Space']],\n"
        "                         ['generate_all', []]]}}), registry)\n"
        "print(json.dumps({'qt': 'PySide6' in sys.modules, 'frame': frame,\n"
        "    'attempts': _attempts}))\n"
    )
)

TABLE_PROBE = (
    BLOCK_QT
    + COUNT_CONNECTIONS
    + (
        "import json\n"
        "from src.gui.main_tabs import audio_suite_surface as s\n"
        "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
        "    'preset_count': len(s.PRESET_NAMES), 'key_count': len(s.KEY_NAMES),\n"
        "    'presets': {n: [list(p) for p in v] for n, v in s.PRESETS.items()},\n"
        "    'keys': dict(s.KEY_MULTIPLIERS),\n"
        "    'name': s.wav_file_name('Deep Space', 'C#'),\n"
        "    'samples': [s.sample_value('Deep Space', i, 0.001, 'C', 55.0,\n"
        "                               1.0, 1.0, 1.0, 0.5) for i in range(8)],\n"
        "    'status': s.run_steps([('select_preset', (0, 'Deep Space')),\n"
        "                           ('generate_all', ())])['state']['drone_status'],\n"
        "    'attempts': _attempts}))\n"
    )
)

SHIPPED_PROBE = BLOCK_QT + (
    "import json\n"
    "from src.gui import audio_suite as a\n"
    "print(json.dumps({'has_qt': a._HAS_QT,\n"
    "    'has_tone_generator': hasattr(a, 'ToneGenerator'),\n"
    "    'has_waveform': hasattr(a, 'WaveformWidget'),\n"
    "    'has_drone_layer': hasattr(a, 'DroneLayer'),\n"
    "    'has_music_panel': hasattr(a, 'MusicPlayerPanel'),\n"
    "    'has_tab': hasattr(a, 'AudioSuiteTab')}))\n"
)

NETWORK_CONTROL_PROBE = COUNT_CONNECTIONS + (
    "import json, socket\n"
    "try:\n"
    "    socket.socket().connect(('127.0.0.1', 9))\n"
    "except OSError:\n"
    "    pass\n"
    "print(json.dumps({'attempts': _attempts}))\n"
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
    assert done.returncode == 0, done.stderr.decode(errors="replace")
    return json.loads(done.stdout.decode(errors="replace").splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the audio tab pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["preset_intervals"] == EXPECTED_PRESETS["Crystal Cave"]
    assert result["key_multiplier"] == EXPECTED_KEY_MULTIPLIERS["A#"]
    assert result["wav_file_name"] == "qat_Crystal_Cave_A#.wav"
    assert result["run"]["state"]["layer_playing"] == [True, False, False, False]
    assert answered["attempts"] == []


def test_the_surface_carries_every_value_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    answered = run_script(TABLE_PROBE)
    assert answered["qt"] is False
    assert answered["preset_count"] == PRESET_TOTAL
    assert answered["key_count"] == KEY_TOTAL
    assert answered["presets"] == EXPECTED_PRESETS
    assert answered["keys"] == EXPECTED_KEY_MULTIPLIERS
    assert answered["name"] == "qat_Deep_Space_C#.wav"
    assert answered["samples"] == [
        surface.sample_value("Deep Space", i, 0.001, "C", 55.0, 1.0, 1.0, 1.0, 0.5)
        for i in range(8)
    ]
    assert "Media: OK" in answered["status"]
    assert answered["attempts"] == []


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script(
        "import sys\nimport PySide6.QtCore\n" + BRIDGE_PROBE.replace(BLOCK_QT, "")
    )
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_qt_block_stops_a_module_that_imports_qt():
    """The Qt block let a module through that imports PySide6."""
    probe = BLOCK_QT + (
        "import json\n"
        "try:\n"
        "    from PySide6.QtWidgets import QLabel\n"
        "    blocked = False\n"
        "except ImportError:\n"
        "    blocked = True\n"
        "print(json.dumps({'blocked': blocked}))\n"
    )
    assert run_script(probe)["blocked"] is True


def test_the_shipped_classes_disappear_where_qt_cannot_be_imported():
    """The shipped tab survives without Qt, so nothing needed replacing."""
    answered = run_script(SHIPPED_PROBE)
    assert answered["has_qt"] is False
    assert answered["has_waveform"] is False
    assert answered["has_drone_layer"] is False
    assert answered["has_music_panel"] is False
    assert answered["has_tone_generator"] is True
    assert answered["has_tab"] is True


def test_the_connection_counter_reaches_a_child_process():
    """The connection counter reported none because it counts nothing.

    The same counter the two probes above carry is pointed at a real
    connection attempt in a child process of its own. It must report one.
    """
    answered = run_script(NETWORK_CONTROL_PROBE)
    assert len(answered["attempts"]) == 1, answered
    assert "127.0.0.1" in answered["attempts"][0], answered


# ---------------------------------------------------------------------
# The surface carries its own copy of every value
# ---------------------------------------------------------------------


def test_the_surface_carries_its_own_copy_of_every_value(monkeypatch):
    """The surface read its values off the module it replaces.

    A surface that imported the shipped tables would follow them, and
    the whole comparison above would be one side read twice. Each
    shipped value is moved and the surface must not move with it.
    """
    moves = (
        (shipped.KEY_MULT, "C", 9.0, 1.0, lambda: surface.KEY_MULTIPLIERS["C"]),
        (shipped.KEY_MULT, "B", 0.5, 1.88775, lambda: surface.KEY_MULTIPLIERS["B"]),
        (
            shipped.ToneGenerator.PRESETS,
            "Deep Space",
            [(9.0, 9.0)],
            [[1.0, 0.30], [1.5, 0.15], [2.0, 0.10], [3.0, 0.05], [1.003, 0.10]],
            lambda: [list(p) for p in surface.PRESETS["Deep Space"]],
        ),
        (
            shipped.ToneGenerator.PRESETS,
            "White Noise Pad",
            [(1.0, 1.0)],
            [[1.0, 0.05], [2.0, 0.05], [3.0, 0.04], [4.0, 0.03], [5.0, 0.03]],
            lambda: [list(p) for p in surface.PRESETS["White Noise Pad"]],
        ),
    )
    for table, key, moved, kept, read in moves:
        was = table[key]
        monkeypatch.setitem(table, key, moved)
        assert table[key] == moved, key
        assert read() == kept, key
        assert read() != moved, key
        monkeypatch.undo()
        assert table[key] == was, key


def test_the_independence_check_names_exactly_what_moved():
    """The independence check moved nothing, so it proves nothing."""
    was = shipped.KEY_MULT["C"]
    shipped.KEY_MULT["C"] = 9.0
    try:
        assert shipped.KEY_MULT["C"] == 9.0
        assert surface.KEY_MULTIPLIERS["C"] == 1.0
        found = differences(dict(shipped.KEY_MULT), dict(surface.KEY_MULTIPLIERS))
        assert found == ["/C: 9.0 against 1.0"], found
    finally:
        shipped.KEY_MULT["C"] = was
    assert differences(dict(shipped.KEY_MULT), dict(surface.KEY_MULTIPLIERS)) == []


def test_the_surface_carries_its_own_copy_of_every_colour(monkeypatch):
    """The surface read its colours off the design system."""
    from src.gui import design_system

    monkeypatch.setattr(design_system, "CARD_METRIC_LABEL", "#123456")
    monkeypatch.setattr(design_system, "SETTINGS_DISABLED_DEEP", "#654321")
    monkeypatch.setattr(design_system, "FOLD_SOURCE_MANUAL", "#abcdef")
    assert surface.SKIN["drone_status"] == "color:#888;font-size:10px;"
    assert surface.SKIN["layer_frame"] == (
        "QFrame{border:1px solid #333333;border-radius:3px;}"
    )
    assert surface.SKIN["music_now_playing"] == "color:#00ccff;font-size:10px;"
    assert "#123456" not in json.dumps(surface.SKIN)


def test_the_shipped_side_mutates_no_shared_state(tmp_path):
    """Reading the shipped tables changed them for the next test."""
    before = digest(
        {
            "keys": dict(shipped.KEY_MULT),
            "presets": {
                name: [list(p) for p in rows]
                for name, rows in shipped.ToneGenerator.PRESETS.items()
            },
        }
    )
    run_shipped(SEQUENCES["every_layer"], MEDIA_READY, tmp_path / "old")
    after = digest(
        {
            "keys": dict(shipped.KEY_MULT),
            "presets": {
                name: [list(p) for p in rows]
                for name, rows in shipped.ToneGenerator.PRESETS.items()
            },
        }
    )
    assert after == before


def test_the_surface_mutates_no_shared_state():
    """Calling the surface changed its own tables."""
    before = digest(
        {
            "keys": dict(surface.KEY_MULTIPLIERS),
            "presets": {
                name: [list(p) for p in rows] for name, rows in surface.PRESETS.items()
            },
            "skin": dict(surface.SKIN),
            "actions": dict(surface.ACTIONS),
        }
    )
    surface.build_view_model("Deep Space", "C", SEQUENCES["every_layer"])
    surface.view_model({"preset": "Ocean Floor", "key": "G"})
    surface.build_view_model()["presets"]["Deep Space"].append([9, 9])
    surface.build_view_model()["skin"]["drone_status"] = "moved"
    surface.preset_answer("Deep Space")[0].append([9, 9])
    after = digest(
        {
            "keys": dict(surface.KEY_MULTIPLIERS),
            "presets": {
                name: [list(p) for p in rows] for name, rows in surface.PRESETS.items()
            },
            "skin": dict(surface.SKIN),
            "actions": dict(surface.ACTIONS),
        }
    )
    assert after == before


def test_a_step_never_edits_the_state_it_was_handed():
    """A step changed the state its caller still holds."""
    state = surface.initial_state()
    before = digest(state)
    moved = surface.apply_step(state, "select_preset", (0, "Deep Space"))
    assert digest(state) == before
    assert moved is not state
    assert moved["layer_presets"] != state["layer_presets"]
    assert state["layer_presets"] == ["", "", "", ""]
    played = surface.apply_step(moved, "generate_all", ())
    assert played is not moved
    assert moved["layer_playing"] == [False] * LAYER_TOTAL
    assert played["layer_playing"] == [True, False, False, False]


def test_the_in_place_check_can_report():
    """The in-place check passes whatever a step does to its state."""
    state = surface.initial_state()
    before = digest(state)
    state["layer_presets"][0] = "Deep Space"
    assert digest(state) != before
    copy = surface.copied_state(state)
    copy["layer_presets"][1] = "Theta Waves"
    assert state["layer_presets"][1] == ""


# ---------------------------------------------------------------------
# One side's world never reaches the other
# ---------------------------------------------------------------------


def test_each_side_gets_its_own_world_and_gives_it_back(tmp_path):
    """A side kept a shared value after its run, or never took one.

    The swap is watched from inside the drive, not only before and
    after: a guard that sets nothing reads the same either side of the
    body.
    """
    outside = world_now()
    seen = []
    with side_world(MEDIA_LIBRARY_MISSING, tmp_path / "first"):
        seen.append(world_now())
        with side_world(MEDIA_READY, tmp_path / "second"):
            seen.append(world_now())
        seen.append(world_now())
    seen.append(world_now())
    assert seen[0]["media_flag"] is False
    assert seen[0]["temp_dir"] == str(tmp_path / "first")
    assert seen[1]["media_flag"] is True
    assert seen[1]["temp_dir"] == str(tmp_path / "second")
    assert seen[2] == seen[0]
    assert seen[3] == outside
    assert seen[0] != outside
    assert seen[1] != seen[0]


def test_a_world_is_given_back_after_a_refusal(tmp_path):
    """A side that refused part way kept its world."""
    outside = world_now()
    inside = {}
    with pytest.raises(RuntimeError):
        with side_world(MEDIA_DEVICE_REFUSED, tmp_path / "refused"):
            inside.update(world_now())
            raise RuntimeError("this drive refused part way")
    assert inside["output"] == "RefusingAudioOutput"
    assert inside["temp_dir"] == str(tmp_path / "refused")
    assert world_now() == outside


def test_a_side_writes_only_into_its_own_directory(tmp_path):
    """One side's written tones landed in the other side's directory."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    run_shipped(SEQUENCES["one_layer"], MEDIA_READY, first)
    written_first = sorted(p.name for p in first.glob("*.wav"))
    run_shipped(SEQUENCES["every_layer"], MEDIA_READY, second)
    written_second = sorted(p.name for p in second.glob("*.wav"))
    assert written_first == ["qat_Deep_Space_C.wav"], written_first
    assert len(written_second) == 4, written_second
    assert sorted(p.name for p in first.glob("*.wav")) == written_first


def test_the_directory_watcher_can_report(tmp_path):
    """The directory watcher sees nothing, so an empty one proves nothing."""
    folder = tmp_path / "watched"
    folder.mkdir()
    assert sorted(p.name for p in folder.glob("*.wav")) == []
    (folder / "qat_planted.wav").write_bytes(b"")
    assert sorted(p.name for p in folder.glob("*.wav")) == ["qat_planted.wav"]


# ---------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------


def test_bridge_registers_the_audio_suite_method():
    """The frontend cannot reach the audio tab."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert METHOD_NAME in registry, sorted(registry)
    assert surface.METHOD == METHOD_NAME
    assert registry[METHOD_NAME] is surface.view_model
    frame = desktop_bridge.handle_line(
        json.dumps({"id": 4, "method": METHOD_NAME, "params": {"key": "G"}}),
        registry,
    )
    assert frame["ok"] is True, frame
    assert frame["result"]["key_multiplier"] == EXPECTED_KEY_MULTIPLIERS["G"]


def test_the_bridge_registration_is_two_lines_and_no_more():
    """The bridge grew more than the import and the one registry line."""
    text = BRIDGE_PATH.read_text(encoding="utf-8")
    named = [line for line in text.splitlines() if "audio_suite_surface" in line]
    assert len(named) == 2, named
    assert named[0].strip() == "audio_suite_surface,"
    assert named[1].strip() == (
        "audio_suite_surface.METHOD: audio_suite_surface.view_model,"
    )


def test_the_bridge_import_list_stays_alphabetical():
    """A surface was added out of order, so the next one lands anywhere."""
    for node in ast.walk(parsed(BRIDGE_PATH)):
        if isinstance(node, ast.ImportFrom) and node.module == "src.gui.main_tabs":
            names = [alias.name for alias in node.names]
            assert names == sorted(names), names
            assert "audio_suite_surface" in names
            return
    raise AssertionError("the bridge imports no surfaces from src.gui.main_tabs")


@pytest.mark.parametrize("preset", EXPECTED_PRESET_NAMES)
def test_the_bridge_carries_every_preset(preset):
    """A preset did not survive the trip across the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    frame = desktop_bridge.handle_line(
        json.dumps({"id": 1, "method": METHOD_NAME, "params": {"preset": preset}}),
        registry,
    )
    assert frame["ok"] is True, frame
    assert frame["result"]["preset_intervals"] == EXPECTED_PRESETS[preset]
    assert frame["result"]["unknown_preset"] == []


@pytest.mark.parametrize("case", sorted(UNKNOWN_NAMES))
def test_the_bridge_reports_an_unknown_name(case):
    """An unknown name came back as if the table held it."""
    payload = surface.view_model({"preset": UNKNOWN_NAMES[case], "key": "C"})
    assert payload["unknown_preset"] == [UNKNOWN_NAMES[case]], case
    assert payload["preset_intervals"] == EXPECTED_PRESETS["Deep Space"], case
    assert payload["requested_preset"] == UNKNOWN_NAMES[case], case


def test_the_payload_crosses_the_bridge_as_json():
    """A value in the payload cannot be written as JSON."""
    payload = surface.build_view_model("Deep Space", "C", SEQUENCES["every_layer"])
    text = json.dumps(payload)
    assert json.loads(text) == json.loads(text)
    assert len(text) > 0


def test_the_bridge_ignores_a_parameter_it_does_not_know():
    """A parameter nothing reads changed the answer."""
    plain = surface.view_model({"preset": "Deep Space"})
    extra = surface.view_model({"preset": "Deep Space", "no_such_thing": 5})
    assert digest(plain) == digest(extra)


def test_the_bridge_reads_a_name_that_is_not_a_string():
    """A number sent where a name belongs was read as that number's text."""
    for value in NON_STRING_NAMES:
        payload = surface.view_model({"preset": value, "key": value})
        assert payload["requested_preset"] == ""
        assert payload["requested_key"] == ""
        assert payload["unknown_preset"] == [""]


def test_the_tables_are_the_same_on_every_call():
    """A second call answered differently from the first."""
    first = surface.view_model({"preset": "Deep Space", "key": "C"})
    second = surface.view_model({"preset": "Deep Space", "key": "C"})
    assert digest(first) == digest(second)


def test_a_media_state_the_surface_does_not_know_opens_ready():
    """An unknown media state was carried into the run."""
    for value in ("no such state", 5, None, [], True):
        state = surface.initial_state(value)
        assert state["media"] == MEDIA_READY, value


# ---------------------------------------------------------------------
# Nothing the surface holds is left out of the snapshot
# ---------------------------------------------------------------------

# Every constant the surface exports, and the payload key that carries
# it. A comparison reading some of them passes whether the rest match or
# not; this closes that gap for every one at once.
PAYLOAD_KEYS = {
    "SAMPLE_RATE_HZ": "sample_rate_hz",
    "CHANNEL_TOTAL": "channel_total",
    "SAMPLE_WIDTH_BYTES": "sample_width_bytes",
    "BYTES_PER_FRAME": "bytes_per_frame",
    "FULL_SCALE": "full_scale",
    "CROSSFADE_S": "crossfade_s",
    "CROSSFADE_BLEND": "crossfade_blend",
    "DEFAULT_DURATION_S": "default_duration_s",
    "GENERATE_VOLUME": "generate_volume",
    "RICHNESS_FLOOR": "richness_floor",
    "RICHNESS_GAIN": "richness_gain",
    "DETUNE_DEPTH": "detune_depth",
    "DETUNE_RATE_HZ": "detune_rate_hz",
    "FREQUENCY_PHASE": "frequency_phase",
    "LFO_DEPTH": "lfo_depth",
    "LFO_RATE_HZ": "lfo_rate_hz",
    "KEY_MULTIPLIERS": "key_multipliers",
    "KEY_NAMES": "key_names",
    "DEFAULT_KEY": "default_key",
    "PRESET_NAMES": "preset_names",
    "FALLBACK_PRESET": "fallback_preset",
    "OFF_LABEL": "off_label",
    "OFF_VALUE": "off_value",
    "LAYER_TOTAL": "layer_total",
    "FIRST_LAYER_VOLUME_PCT": "first_layer_volume_pct",
    "OTHER_LAYER_VOLUME_PCT": "other_layer_volume_pct",
    "VOLUME_RANGE_PCT": "volume_range_pct",
    "VOLUME_LABEL_WIDTH_PX": "volume_label_width_px",
    "BASE_FREQUENCY_INDEX": "base_frequency_index",
    "DETUNE_RANGE": "detune_range",
    "DETUNE_DEFAULT": "detune_default",
    "DETUNE_DIVISOR": "detune_divisor",
    "DETUNE_TOOLTIP": "detune_tooltip",
    "LFO_RANGE": "lfo_range",
    "LFO_DEFAULT": "lfo_default",
    "LFO_DIVISOR": "lfo_divisor",
    "LFO_TOOLTIP": "lfo_tooltip",
    "RICHNESS_RANGE": "richness_range",
    "RICHNESS_DEFAULT": "richness_default",
    "RICHNESS_DIVISOR": "richness_divisor",
    "RICHNESS_TOOLTIP": "richness_tooltip",
    "MUSIC_TITLE": "music_title",
    "DRONE_TITLE": "drone_title",
    "MUSIC_BUTTON_LABELS": "music_button_labels",
    "DRONE_BUTTON_LABELS": "drone_button_labels",
    "KEY_UP_TOOLTIP": "key_up_tooltip",
    "CONTROL_LABELS": "control_labels",
    "PLAY_LABEL": "play_label",
    "PAUSE_LABEL": "pause_label",
    "NOTHING_PLAYING_TEXT": "nothing_playing_text",
    "NOW_PLAYING_FORMAT": "now_playing_format",
    "MUSIC_LIST_MAX_HEIGHT_PX": "music_list_max_height_px",
    "MUSIC_VOLUME_DEFAULT_PCT": "music_volume_default_pct",
    "FILE_DIALOG_TITLE": "file_dialog_title",
    "FILE_DIALOG_FILTER": "file_dialog_filter",
    "MEDIA_MISSING_TEXT": "media_missing_text",
    "DRONE_OPENING_STATUS": "drone_opening_status",
    "GENERATING_TEXT": "generating_text",
    "STOPPED_TEXT": "stopped_text",
    "SHIFTING_FORMAT": "shifting_format",
    "LAYER_LABEL_FORMAT": "layer_label_format",
    "VOLUME_LABEL_FORMAT": "volume_label_format",
    "NO_WAV_FORMAT": "no_wav_format",
    "DRONE_ERROR_FORMAT": "drone_error_format",
    "DRONE_PLAYING_FORMAT": "drone_playing_format",
    "MEDIA_PRESENT_TEXT": "media_present_text",
    "MEDIA_ABSENT_TEXT": "media_absent_text",
    "WAV_NAME_FORMAT": "wav_name_format",
    "WAV_DIRECTORY_SOURCE": "wav_directory_source",
    "PRESET_NAME_SPACE": "preset_name_space",
    "PRESET_NAME_SPACE_REPLACEMENT": "preset_name_space_replacement",
    "PRESET_NAME_SHARP": "preset_name_sharp",
    "PRESET_NAME_SHARP_REPLACEMENT": "preset_name_sharp_replacement",
    "WAVEFORM_MIN_HEIGHT_PX": "waveform_min_height_px",
    "WAVEFORM_MAX_HEIGHT_PX": "waveform_max_height_px",
    "WAVEFORM_IDLE_TEXT": "waveform_idle_text",
    "WAVEFORM_KEY_FORMAT": "waveform_key_format",
    "WAVEFORM_BACKGROUND_TOP": "waveform_background_top",
    "WAVEFORM_BACKGROUND_BOTTOM": "waveform_background_bottom",
    "WAVEFORM_IDLE_COLOUR": "waveform_idle_colour",
    "WAVEFORM_KEY_COLOUR": "waveform_key_colour",
    "WAVEFORM_IDLE_FONT": "waveform_idle_font",
    "WAVEFORM_KEY_FONT": "waveform_key_font",
    "WAVEFORM_KEY_INSET_PX": "waveform_key_inset_px",
    "WAVEFORM_KEY_BASELINE_PX": "waveform_key_baseline_px",
    "LAYER_TRACE_COLOURS": "layer_trace_colours",
    "LAYER_TRACE_ALPHA": "layer_trace_alpha",
    "LAYER_TRACE_WIDTH_PX": "layer_trace_width_px",
    "LAYER_TRACE_STEP_PX": "layer_trace_step_px",
    "TRACE_AMPLITUDE_BASE_PX": "trace_amplitude_base_px",
    "TRACE_AMPLITUDE_STEP_PX": "trace_amplitude_step_px",
    "TRACE_CYCLES": "trace_cycles",
    "TRACE_RATE_BASE": "trace_rate_base",
    "TRACE_RATE_STEP": "trace_rate_step",
    "TRACE_PHASE_STEP": "trace_phase_step",
    "ANIMATION_STEP_S": "animation_step_s",
    "ANIMATION_PHASE_GAIN": "animation_phase_gain",
    "SPLITTER_SIZES_PX": "splitter_sizes_px",
    "SPLITTER_HANDLE_WIDTH_PX": "splitter_handle_width_px",
    "SPLITTER_CHILDREN_COLLAPSIBLE": "splitter_children_collapsible",
    "TAB_MARGINS_PX": "tab_margins_px",
    "TAB_SPACING_PX": "tab_spacing_px",
    "ACCESSIBLE_NAMES": "accessible_names",
    "SKIN": "skin",
    "EQUAL_CHANNEL_COLOURS": "equal_channel_colours",
    "ACTIONS": "actions",
    "TIMERS": "timers",
    "TIMER_DELAYS_MS": "timer_delays_ms",
    "BUS_TOPICS": "bus_topics",
    "SIGNALS": "signals",
    "THREAD_TOTAL": "thread_total",
    "STEP_NAMES": "step_names",
    "LAYER_STEPS": "layer_steps",
    "DRONE_STEPS": "drone_steps",
    "MUSIC_STEPS": "music_steps",
    "WAVEFORM_STEPS": "waveform_steps",
    "MEDIA_STATES": "media_states",
    "SLIDER_MIN": "slider_min",
    "SLIDER_MAX": "slider_max",
    "NOTHING_CHOSEN_INDEX": "nothing_chosen_index",
    "MISSING_CONTROL_FORMAT": "missing_control_format",
    "PRESETS": "presets",
    "BASE_FREQUENCIES": "base_frequencies",
}

# The constants no snapshot key carries, each with the check that covers
# it.
NOT_IN_THE_SNAPSHOT = {
    "METHOD": "test_bridge_registers_the_audio_suite_method",
    "NOT_ASKED": "test_a_name_that_is_not_text_asks_for_nothing",
    "NO_REFUSAL": "test_a_sequence_that_refuses_stops_at_the_same_step",
    "NOT_STOPPED": "test_both_sides_end_one_sequence_in_the_same_state",
    "UNKNOWN_STEP_REFUSAL": "test_a_sequence_that_refuses_stops_at_the_same_step",
    "MEDIA_READY": "test_a_media_state_the_surface_does_not_know_opens_ready",
    "MEDIA_DEVICE_REFUSED": (
        "test_a_device_that_refuses_leaves_the_controls_and_plays_nothing"
    ),
    "MEDIA_LIBRARY_MISSING": (
        "test_the_music_controls_are_absent_without_the_sound_library"
    ),
    "NO_CHOICE": "test_a_key_no_list_holds_is_reported_as_nothing_chosen",
}

REQUEST_ONLY_KEYS = {
    "requested_preset",
    "requested_key",
    "requested_media",
    "preset_intervals",
    "preset_refusal",
    "key_multiplier",
    "key_refusal",
    "unknown_preset",
    "unknown_key",
    "wav_file_name",
    "run",
}

CONSTANT_TYPES = (str, int, float, bool, dict, tuple, type(None))


def plain(value):
    """One value with every tuple turned into a list, at every depth.

    A table crosses the bridge as JSON, where a tuple arrives as a list.
    Comparing the two forms directly reports a difference that is not
    one.
    """
    if isinstance(value, dict):
        return {key: plain(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(inner) for inner in value]
    return value


def surface_constants():
    """Every value the surface exports that is not a function or a class."""
    return {
        name: value
        for name, value in vars(surface).items()
        if not name.startswith("_")
        and not callable(value)
        and isinstance(value, CONSTANT_TYPES)
    }


def test_every_constant_the_surface_holds_reaches_the_snapshot():
    """A constant the surface exports is in no snapshot the tests read."""
    payload = surface.build_view_model()
    constants = surface_constants()
    unaccounted = []
    for name, value in constants.items():
        if name in PAYLOAD_KEYS:
            carried = payload[PAYLOAD_KEYS[name]]
            assert plain(carried) == plain(value), name
        elif name in NOT_IN_THE_SNAPSHOT:
            covered_by = NOT_IN_THE_SNAPSHOT[name]
            assert covered_by in globals(), (name, covered_by)
            assert callable(globals()[covered_by]), (name, covered_by)
        else:
            unaccounted.append(name)
    assert unaccounted == [], unaccounted
    assert len(constants) == len(PAYLOAD_KEYS) + len(NOT_IN_THE_SNAPSHOT), (
        len(constants),
        len(PAYLOAD_KEYS),
        len(NOT_IN_THE_SNAPSHOT),
    )


def test_every_snapshot_key_carries_a_constant_the_surface_holds():
    """The snapshot grew a key no constant on the surface backs."""
    payload = surface.build_view_model()
    assert set(payload) == set(PAYLOAD_KEYS.values()) | REQUEST_ONLY_KEYS, sorted(
        set(payload) ^ (set(PAYLOAD_KEYS.values()) | REQUEST_ONLY_KEYS)
    )
    assert set(PAYLOAD_KEYS.values()) & REQUEST_ONLY_KEYS == set()
    for key in REQUEST_ONLY_KEYS:
        assert key in payload, key


def test_the_completeness_checks_can_report():
    """The completeness checks passed because they look at nothing.

    A constant that reaches no snapshot key and no named exception must
    land in the unaccounted list, and a payload key backed by nothing
    must fall outside the two named sets.
    """
    invented = "INVENTED_CONSTANT"
    assert invented not in PAYLOAD_KEYS
    assert invented not in NOT_IN_THE_SNAPSHOT
    assert invented not in surface_constants()
    assert "PRESETS" in surface_constants()
    assert "SKIN" in surface_constants()
    assert "sample_value" not in surface_constants()
    assert "view_model" not in surface_constants()
    assert "UnknownStep" not in surface_constants()
    payload = surface.build_view_model()
    assert "invented_key" not in payload
    assert "invented_key" not in set(PAYLOAD_KEYS.values()) | REQUEST_ONLY_KEYS


def test_a_key_no_list_holds_is_reported_as_nothing_chosen(tmp_path):
    """A key the list does not hold read as a chosen one on either side."""
    steps = [("select_key", ("H",)), ("select_base", ("999Hz",))]
    old = run_shipped(steps, MEDIA_READY, tmp_path / "old")
    new = run_surface(steps, MEDIA_READY)
    assert old["state"]["key_index"] == surface.NOTHING_CHOSEN_INDEX
    assert old["state"]["base_index"] == surface.NOTHING_CHOSEN_INDEX
    assert differences(old["state"], new["state"]) == []
    assert surface.current_key(new["state"]) is surface.NO_CHOICE
    assert surface.current_base_freq(new["state"]) is surface.NO_CHOICE
    assert surface.key_text(surface.NO_CHOICE) == ""
    chosen = run_surface([("select_key", ("A#",))], MEDIA_READY)["state"]
    assert surface.current_key(chosen) == "A#"
    assert surface.current_base_freq(chosen) == 55


# ---------------------------------------------------------------------
# The wording the drone panel shows
# ---------------------------------------------------------------------


def direct_children(widget, kind):
    """The `kind` widgets `widget` owns itself, in the order it built them."""
    from PySide6.QtCore import Qt

    return widget.findChildren(
        kind, options=Qt.FindChildOption.FindDirectChildrenOnly
    )


def shown_texts(widget, kind):
    """The text on each `kind` widget `widget` owns itself."""
    return [one.text() for one in direct_children(widget, kind)]


def test_the_drone_buttons_carry_the_labels_the_surface_publishes(tmp_path):
    """A renderer drew a drone button from wording no table holds."""
    from PySide6.QtWidgets import QPushButton

    app()
    with side_world(MEDIA_READY, tmp_path / "buttons"):
        panel = shipped.DroneEnginePanel()
        try:
            painted = shown_texts(panel, QPushButton)
        finally:
            panel.deleteLater()
    assert painted == list(surface.DRONE_BUTTON_LABELS), (
        "the drone panel paints "
        f"{painted}, the surface publishes {list(surface.DRONE_BUTTON_LABELS)}"
    )


def test_the_key_up_button_carries_the_tooltip_the_surface_publishes(tmp_path):
    """The one drone button with a tooltip explained itself off-table."""
    from PySide6.QtWidgets import QPushButton

    app()
    at = surface.DRONE_BUTTON_LABELS.index(surface.DRONE_BUTTON_LABELS[-1])
    with side_world(MEDIA_READY, tmp_path / "tooltip"):
        panel = shipped.DroneEnginePanel()
        try:
            buttons = direct_children(panel, QPushButton)
            painted = [one.toolTip() for one in buttons]
        finally:
            panel.deleteLater()
    assert painted[at] == surface.KEY_UP_TOOLTIP, (
        f"the key-up button says {painted[at]!r}, "
        f"the surface publishes {surface.KEY_UP_TOOLTIP!r}"
    )
    assert [one for one in painted if one] == [surface.KEY_UP_TOOLTIP], painted


def test_every_control_label_the_panels_show_is_one_the_surface_publishes(tmp_path):
    """A slider or a list was labelled with wording no table holds."""
    from PySide6.QtWidgets import QLabel

    app()
    with side_world(MEDIA_READY, tmp_path / "labels"):
        drone = shipped.DroneEnginePanel()
        music = shipped.MusicPlayerPanel()
        try:
            painted = shown_texts(drone, QLabel) + shown_texts(music, QLabel)
            painted += shown_texts(drone._layers[0], QLabel)
        finally:
            drone.deleteLater()
            music.deleteLater()
    published = set(surface.CONTROL_LABELS.values())
    off_table = [one for one in painted if one.endswith(":") and one not in published]
    assert off_table == [], (
        f"{len(off_table)} control labels reach no table: {off_table}. "
        f"The surface publishes {sorted(published)}"
    )
    assert published <= set(painted), sorted(published - set(painted))


def test_the_label_check_names_a_control_the_surface_has_no_wording_for():
    """The check passed because it compared two empty collections."""
    published = set(surface.CONTROL_LABELS.values())
    assert published, "the surface publishes no control wording at all"
    invented = "Nothing:"
    assert invented not in published
    painted = list(published) + [invented]
    off_table = [one for one in painted if one.endswith(":") and one not in published]
    assert off_table == [invented], off_table
