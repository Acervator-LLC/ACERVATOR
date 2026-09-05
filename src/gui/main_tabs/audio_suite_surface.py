"""audio_suite_surface.py -- the music player and the ambient drone engine
as values, with no sound and no window.

The tab this replaces holds two panels. The music player keeps a list of
files and plays one at a time. The drone engine keeps four layers, each
with a preset and a volume, and builds a looping tone for every layer
that has a preset chosen.

Nothing here opens an audio device, writes a file or reads the clock.
``wav_file_name`` returns the NAME the shipped generator would write and
``WAV_DIRECTORY_SOURCE`` names where that name would be joined, both as
text. ``sample_value`` returns one whole number of the tone the shipped
generator would write at one position, so the sound can be compared
without a file and without a device.

``run_steps`` drives a named sequence of screen actions over
``initial_state`` and returns the state after each one. A step handed a
value it cannot use stops the sequence, and the answer names the step
index, the step name and the kind of refusal. Neither ``apply_step`` nor
``run_steps`` changes the state it is given.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``audio_suite.state`` method, which is how the Electron renderer
reaches it. Every value below is written out here rather than read from
``src.gui.audio_suite`` or from ``src.gui.design_system``, so a value
changed on one side alone is reported. Nothing here imports Qt.
"""

from __future__ import annotations

import math
import os
from typing import Any

METHOD = "audio_suite.state"

SAMPLE_RATE_HZ = 44100

CHANNEL_TOTAL = 2

SAMPLE_WIDTH_BYTES = 2

BYTES_PER_FRAME = 4

FULL_SCALE = 32767

CROSSFADE_S = 2.0

CROSSFADE_BLEND = 0.3

DEFAULT_DURATION_S = 30.0

GENERATE_VOLUME = 0.8

RICHNESS_FLOOR = 0.5

RICHNESS_GAIN = 0.1

DETUNE_DEPTH = 0.003

DETUNE_RATE_HZ = 0.1

FREQUENCY_PHASE = 0.01

LFO_DEPTH = 0.1

LFO_RATE_HZ = 0.05

KEY_MULTIPLIERS: dict[str, float] = {
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

KEY_NAMES = tuple(KEY_MULTIPLIERS)

DEFAULT_KEY = "C"

PRESETS: dict[str, tuple[tuple[float, float], ...]] = {
    "Deep Space": (
        (1.0, 0.30),
        (1.5, 0.15),
        (2.0, 0.10),
        (3.0, 0.05),
        (1.003, 0.10),
    ),
    "Theta Waves": ((1.0, 0.20), (1.03, 0.20), (0.5, 0.10), (0.515, 0.10)),
    "Crystal Cave": (
        (1.0, 0.15),
        (1.222, 0.10),
        (1.479, 0.08),
        (0.5, 0.12),
        (0.611, 0.06),
    ),
    "Ocean Floor": (
        (1.0, 0.25),
        (1.5, 0.15),
        (2.0, 0.10),
        (1.007, 0.15),
        (3.0, 0.05),
    ),
    "Quantum Field": (
        (1.0, 0.20),
        (2.0, 0.10),
        (0.5, 0.15),
        (1.002, 0.10),
        (1.5, 0.08),
    ),
    "Solar Wind": (
        (1.0, 0.15),
        (1.636, 0.10),
        (2.273, 0.08),
        (1.002, 0.10),
        (0.5, 0.12),
    ),
    "Meditation Bell": (
        (1.0, 0.20),
        (2.0, 0.08),
        (3.0, 0.04),
        (0.5, 0.10),
        (1.001, 0.05),
    ),
    "White Noise Pad": (
        (1.0, 0.05),
        (2.0, 0.05),
        (3.0, 0.04),
        (4.0, 0.03),
        (5.0, 0.03),
    ),
}

PRESET_NAMES = tuple(PRESETS)

FALLBACK_PRESET = "Deep Space"

OFF_LABEL = "(off)"

OFF_VALUE = ""

LAYER_TOTAL = 4

FIRST_LAYER_VOLUME_PCT = 50

OTHER_LAYER_VOLUME_PCT = 30

VOLUME_RANGE_PCT = (0, 100)

VOLUME_LABEL_WIDTH_PX = 30

BASE_FREQUENCIES: tuple[tuple[str, float], ...] = (
    ("27.5Hz", 27.5),
    ("55Hz", 55),
    ("110Hz", 110),
    ("220Hz", 220),
)

BASE_FREQUENCY_INDEX = 1

DETUNE_RANGE = (0, 100)

DETUNE_DEFAULT = 50

DETUNE_DIVISOR = 50

DETUNE_TOOLTIP = "0=none, 100=heavy chorus"

LFO_RANGE = (10, 300)

LFO_DEFAULT = 100

LFO_DIVISOR = 100

LFO_TOOLTIP = "Speed: 10=slow, 300=fast"

RICHNESS_RANGE = (0, 100)

RICHNESS_DEFAULT = 30

RICHNESS_DIVISOR = 100

RICHNESS_TOOLTIP = "0=pure sine, 100=rich overtones"

MUSIC_TITLE = "Music Player"

DRONE_TITLE = "Ambient Drone Engine"

MUSIC_BUTTON_LABELS = ("Add", "Play", "Stop", "Next")

DRONE_BUTTON_LABELS = ("Generate All", "Play All", "Stop All", "Key +1")

KEY_UP_TOOLTIP = "Shift key up and regenerate"

# The wording beside one control. No other table carries it, so a screen
# built from the payload alone has unlabelled sliders and lists.
CONTROL_LABELS = {
    "volume": "Vol:",
    "key": "Key:",
    "base": "Base:",
    "detune": "Detune:",
    "lfo": "LFO:",
    "richness": "Rich:",
}

PLAY_LABEL = "Play"

PAUSE_LABEL = "Pause"

NOTHING_PLAYING_TEXT = "Nothing playing"

NOW_PLAYING_FORMAT = "Playing: {}"

MUSIC_LIST_MAX_HEIGHT_PX = 100

MUSIC_VOLUME_DEFAULT_PCT = 50

FILE_DIALOG_TITLE = "Music"

FILE_DIALOG_FILTER = "Audio (*.mp3 *.wav *.ogg *.flac *.m4a)"

MEDIA_MISSING_TEXT = "Qt Multimedia not available.\npip install PySide6-Multimedia"

DRONE_OPENING_STATUS = "Select presets per layer, then Generate All"

GENERATING_TEXT = "Generating..."

STOPPED_TEXT = "Stopped"

SHIFTING_FORMAT = "Shifting to {}..."

LAYER_LABEL_FORMAT = "Layer {}"

VOLUME_LABEL_FORMAT = "{}%"

NO_WAV_FORMAT = "L{}: no WAV"

DRONE_ERROR_FORMAT = "{} layer(s) — ERRORS: {}"

DRONE_PLAYING_FORMAT = (
    "{count} layer(s) playing in {key} | det={detune}% lfo={lfo}% rich={richness}%"
    " | Media: {media}"
)

MEDIA_PRESENT_TEXT = "OK"

MEDIA_ABSENT_TEXT = "UNAVAILABLE"

WAV_NAME_FORMAT = "qat_{}_{}.wav"

WAV_DIRECTORY_SOURCE = "tempfile.gettempdir()"

PRESET_NAME_SPACE = " "

PRESET_NAME_SPACE_REPLACEMENT = "_"

PRESET_NAME_SHARP = "#"

PRESET_NAME_SHARP_REPLACEMENT = "s"

WAVEFORM_MIN_HEIGHT_PX = 50

WAVEFORM_MAX_HEIGHT_PX = 70

WAVEFORM_IDLE_TEXT = "Audio idle"

WAVEFORM_KEY_FORMAT = "Key: {}"

WAVEFORM_BACKGROUND_TOP = "#08080e"

WAVEFORM_BACKGROUND_BOTTOM = "#0c0c16"

WAVEFORM_IDLE_COLOUR = "#323246"

WAVEFORM_KEY_COLOUR = "#64648c"

WAVEFORM_IDLE_FONT = ("Segoe UI", 9)

WAVEFORM_KEY_FONT = ("Consolas", 8)

WAVEFORM_KEY_INSET_PX = 60

WAVEFORM_KEY_BASELINE_PX = 4

LAYER_TRACE_COLOURS = ("#00c8ff", "#00ffa0", "#ffb400", "#c864ff")

LAYER_TRACE_ALPHA = 100

LAYER_TRACE_WIDTH_PX = 1.2

LAYER_TRACE_STEP_PX = 2

TRACE_AMPLITUDE_BASE_PX = 15

TRACE_AMPLITUDE_STEP_PX = 5

TRACE_CYCLES = 4

TRACE_RATE_BASE = 0.8

TRACE_RATE_STEP = 0.4

TRACE_PHASE_STEP = 1.2

ANIMATION_STEP_S = 0.033

ANIMATION_PHASE_GAIN = 2

SPLITTER_SIZES_PX = (300, 500)

SPLITTER_HANDLE_WIDTH_PX = 5

SPLITTER_CHILDREN_COLLAPSIBLE = False

TAB_MARGINS_PX = (4, 4, 4, 4)

TAB_SPACING_PX = 4

ACCESSIBLE_NAMES = {
    "waveform": "Waveform Widget",
    "layer": "Drone Layer",
    "music_panel": "Music Player Panel",
    "drone_panel": "",
    "tab": "Audio Suite Tab",
}

SKIN = {
    "layer_frame": "QFrame{border:1px solid #333333;border-radius:3px;}",
    "music_play_button": "font-weight:bold;",
    "music_now_playing": "color:#00ccff;font-size:10px;",
    "drone_play_all_button": "font-weight:bold;color:#00ccff;",
    "drone_status": "color:#888;font-size:10px;",
}

# Colours whose red, green and blue are not all different. A swap of two
# matching channels paints the same pixel, so each is read as text.
EQUAL_CHANNEL_COLOURS = (
    "drone_status",
    "layer_frame",
    "waveform_background_top",
    "waveform_background_bottom",
    "waveform_idle_colour",
    "waveform_key_colour",
)

ACTIONS = {
    "layer_volume_changed": "set the layer volume and its label",
    "music_add_clicked": "choose music files and list them",
    "music_play_pause_clicked": "start the chosen track or pause the playing one",
    "music_stop_clicked": "stop the music player",
    "music_next_clicked": "play the next track in the list",
    "music_volume_changed": "set the music player volume",
    "music_media_status_changed": "play the next track when one ends",
    "drone_generate_all_clicked": "build and start every layer that has a preset",
    "drone_play_all_clicked": "build and start every layer that has a preset",
    "drone_stop_all_clicked": "stop every layer",
    "drone_key_up_clicked": "shift the key up one step and build again",
    "layer_state_changed": "count the playing layers and report the key",
    "layer_media_status_changed": "start a layer again when its tone ends",
    "layer_error_occurred": "mark a layer stopped after a player error",
    "layer_playback_state_changed": "mark a layer stopped after the player stops",
    "drone_state_changed": "hand the layer count and the key to the waveform",
    "waveform_tick": "move the waveform on by one animation step",
}

TIMERS = {"waveform_animation": 33}

TIMER_DELAYS_MS = (33,)

BUS_TOPICS: tuple[str, ...] = ()

SIGNALS = ("state_changed", "drone_state")

THREAD_TOTAL = 0

NOT_ASKED = ""

NO_CHOICE = None

NOTHING_CHOSEN_INDEX = -1

# A slider hands its setting to a signed four-byte whole number. Measured
# on QSlider.setValue: -2147483648 and 2147483647 are taken, either
# neighbour is refused.
SLIDER_MIN = -2147483648

SLIDER_MAX = 2147483647

MEDIA_READY = "ready"

MEDIA_DEVICE_REFUSED = "device_refused"

MEDIA_LIBRARY_MISSING = "library_missing"

MEDIA_STATES = (MEDIA_READY, MEDIA_DEVICE_REFUSED, MEDIA_LIBRARY_MISSING)

MISSING_CONTROL_FORMAT = "the music player has no {} without the sound library"

LAYER_STEPS = (
    "select_preset",
    "set_layer_volume",
    "layer_ended",
    "layer_error",
)

DRONE_STEPS = (
    "set_detune",
    "set_lfo",
    "set_richness",
    "select_key",
    "select_base",
    "generate_all",
    "stop_all",
    "key_up",
)

MUSIC_STEPS = (
    "add_files",
    "play_index",
    "toggle_music",
    "next_track",
    "music_ended",
    "stop_music",
    "set_music_volume",
)

WAVEFORM_STEPS = ("animate",)

STEP_NAMES = LAYER_STEPS + DRONE_STEPS + MUSIC_STEPS + WAVEFORM_STEPS

NO_REFUSAL = ""

NOT_STOPPED = -1

UNKNOWN_STEP_REFUSAL = "UnknownStep"


class UnknownStep(LookupError):
    """The sequence named a step this surface does not run."""


def key_multiplier(key: Any) -> float:
    """The frequency multiplier for a musical key, or 1.0 for any other name.

    Raises TypeError for a value a table cannot be keyed by, as the
    shipped generator does.
    """
    return KEY_MULTIPLIERS.get(key, 1.0)


def preset_intervals(name: Any) -> tuple[tuple[float, float], ...]:
    """One preset's interval and loudness pairs, or the fallback preset's.

    Raises TypeError for a value a table cannot be keyed by.
    """
    return PRESETS.get(name, PRESETS[FALLBACK_PRESET])


def has_preset(name: Any) -> bool:
    """Whether the table holds a preset under `name`."""
    return isinstance(name, str) and name in PRESETS


def has_key(name: Any) -> bool:
    """Whether the table holds a key multiplier under `name`."""
    return isinstance(name, str) and name in KEY_MULTIPLIERS


def whole_number(value: Any) -> int:
    """One whole number a slider will take, refusing what a slider refuses.

    A true or false is taken as one or nothing. A decimal is cut to a
    whole number. Anything else raises TypeError, and a number outside a
    signed four-byte whole number raises OverflowError.
    """
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        cut = value
    elif isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise OverflowError("a slider takes no value without a size")
        cut = int(value)
    else:
        raise TypeError("a slider takes a number, not " + type(value).__name__)
    if cut < SLIDER_MIN or cut > SLIDER_MAX:
        raise OverflowError("a slider takes no number this large")
    return cut


def slider_value(value: Any, low: Any, high: Any) -> int:
    """A slider setting held inside its own range, as a slider holds it."""
    return max(low, min(high, whole_number(value)))


def has_player(media: Any) -> bool:
    """Whether the sound library loaded and the device opened."""
    return media == MEDIA_READY


def has_music_controls(media: Any) -> bool:
    """Whether the music panel built its list, its buttons and its slider."""
    return media != MEDIA_LIBRARY_MISSING


def missing_control(media: Any, control: str) -> None:
    """Refuse a music control the panel never built. Otherwise do nothing."""
    if not has_music_controls(media):
        raise AttributeError(MISSING_CONTROL_FORMAT.format(control))


def chosen_preset(name: Any) -> Any:
    """The preset a layer holds after a choice.

    The empty text is the off item. A name the list holds is itself. Any
    other value picks no item at all, which the layer reads as nothing.
    """
    if name == OFF_VALUE:
        return OFF_VALUE
    if has_preset(name):
        return name
    return NO_CHOICE


def key_index_for(name: Any) -> int:
    """Where a key sits in the list, or -1 when the list does not hold it."""
    return KEY_NAMES.index(name) if has_key(name) else NOTHING_CHOSEN_INDEX


def base_index_for(label: Any) -> int:
    """Where a base frequency sits, or -1 when the list does not hold it."""
    labels = [row[0] for row in BASE_FREQUENCIES]
    return labels.index(label) if label in labels else NOTHING_CHOSEN_INDEX


def layer_volume_pct(index: Any) -> int:
    """The volume a layer opens at. The first layer opens louder."""
    return FIRST_LAYER_VOLUME_PCT if index == 0 else OTHER_LAYER_VOLUME_PCT


def layer_label(index: Any) -> str:
    """The heading over one layer, counted from one."""
    return LAYER_LABEL_FORMAT.format(index + 1)


def volume_label(percent: Any) -> str:
    """The text beside a volume slider."""
    return VOLUME_LABEL_FORMAT.format(percent)


def output_volume(percent: Any) -> float:
    """The volume the audio output is set to, as a part of one."""
    return percent / 100


def effect_values(detune_pct: Any, lfo_pct: Any, richness_pct: Any) -> dict:
    """The three slider readings turned into the numbers the tone uses."""
    return {
        "detune": detune_pct / DETUNE_DIVISOR,
        "lfo_speed": lfo_pct / LFO_DIVISOR,
        "richness": richness_pct / RICHNESS_DIVISOR,
    }


def safe_preset_name(name: Any) -> str:
    """A preset name with the characters a file name cannot hold taken out.

    Raises AttributeError for a value that is not text.
    """
    return name.replace(PRESET_NAME_SPACE, PRESET_NAME_SPACE_REPLACEMENT).replace(
        PRESET_NAME_SHARP, PRESET_NAME_SHARP_REPLACEMENT
    )


def wav_file_name(preset: Any, key: Any) -> str:
    """The file name the shipped generator writes for one preset and key.

    The name only. ``WAV_DIRECTORY_SOURCE`` names where the shipped code
    joins it. The key is written in as it arrives, which is what the
    shipped generator does.
    """
    return WAV_NAME_FORMAT.format(safe_preset_name(preset), key)


def now_playing_text(path: Any) -> str:
    """The caption under the music list while a track plays."""
    return NOW_PLAYING_FORMAT.format(os.path.basename(path))


def frame_total(duration_s: Any) -> int:
    """How many frames of tone are written for one length in seconds."""
    return int(SAMPLE_RATE_HZ * duration_s)


def crossfade_frames() -> int:
    """How many frames the loop join covers."""
    return int(SAMPLE_RATE_HZ * CROSSFADE_S)


def unblended_sample(
    preset: Any,
    index: Any,
    duration_s: Any,
    key: Any,
    base_freq: Any,
    detune: Any,
    lfo_speed: Any,
    richness: Any,
    master_volume: Any,
) -> int:
    """One whole number of the tone before the loop join is mixed in.

    Sums one wave for every interval of the preset, bends each by the
    detune amount, breathes each with the slow wave, adds a second
    harmonic above the richness floor, holds the sum inside one, and
    fades the tail that runs past the written length.
    """
    intervals = preset_intervals(preset)
    multiplier = key_multiplier(key)
    written = frame_total(duration_s)
    join = crossfade_frames()
    seconds = index / SAMPLE_RATE_HZ
    total = 0.0
    for interval, loudness in intervals:
        frequency = base_freq * interval * multiplier
        bent = frequency * (
            1.0
            + (detune - 1.0)
            * DETUNE_DEPTH
            * math.sin(DETUNE_RATE_HZ * seconds + frequency * FREQUENCY_PHASE)
        )
        breath = 1.0 + LFO_DEPTH * math.sin(
            2 * math.pi * LFO_RATE_HZ * lfo_speed * seconds
            + frequency * FREQUENCY_PHASE
        )
        total += loudness * breath * math.sin(2 * math.pi * bent * seconds)
        if richness > RICHNESS_FLOOR:
            total += (
                loudness
                * RICHNESS_GAIN
                * (richness - RICHNESS_FLOOR)
                * math.sin(2 * math.pi * bent * 2 * seconds)
            )
    total = max(-1.0, min(1.0, total * master_volume))
    if index >= written:
        total *= 1.0 - ((index - written) / join)
    return int(total * FULL_SCALE)


def sample_value(
    preset: Any,
    index: Any,
    duration_s: Any = DEFAULT_DURATION_S,
    key: Any = DEFAULT_KEY,
    base_freq: Any = 55.0,
    detune: Any = 1.0,
    lfo_speed: Any = 1.0,
    richness: Any = 1.0,
    master_volume: Any = GENERATE_VOLUME,
) -> int:
    """One whole number of the written tone at one frame position.

    Inside the loop join the tail of the tone is mixed into the head, so
    the tone repeats without a click. Past the join the value is the
    plain one.
    """
    head = unblended_sample(
        preset,
        index,
        duration_s,
        key,
        base_freq,
        detune,
        lfo_speed,
        richness,
        master_volume,
    )
    join = crossfade_frames()
    if index >= join:
        return head
    part = index / join
    tail = unblended_sample(
        preset,
        frame_total(duration_s) + index,
        duration_s,
        key,
        base_freq,
        detune,
        lfo_speed,
        richness,
        master_volume,
    )
    mixed = int(head * (1 - part * CROSSFADE_BLEND) + tail * part * CROSSFADE_BLEND)
    return max(-FULL_SCALE, min(FULL_SCALE, mixed))


def next_key_index(index: Any) -> int:
    """The key one step up, wrapping past the last one."""
    return (index + 1) % len(KEY_NAMES)


def drone_status(
    started: Any, key: Any, detune_pct: Any, lfo_pct: Any, richness_pct: Any, media: Any
) -> str:
    """The line under the drone engine when every layer built a tone."""
    return DRONE_PLAYING_FORMAT.format(
        count=started,
        key=key,
        detune=detune_pct,
        lfo=lfo_pct,
        richness=richness_pct,
        media=MEDIA_PRESENT_TEXT if media else MEDIA_ABSENT_TEXT,
    )


def drone_error_status(started: Any, errors: Any) -> str:
    """The line under the drone engine when a layer built no tone."""
    return DRONE_ERROR_FORMAT.format(started, "; ".join(errors))


def initial_state(media: Any = MEDIA_READY) -> dict:
    """The tab as it opens, with no preset chosen and nothing playing.

    `media` is one of the three states. With the library missing the
    music player carries one line of text and no controls. With the
    device refused the controls are there and reach no player. Only the
    ready state plays anything.
    """
    return {
        "media": media if media in MEDIA_STATES else MEDIA_READY,
        "layer_presets": [OFF_VALUE] * LAYER_TOTAL,
        "layer_volumes_pct": [layer_volume_pct(i) for i in range(LAYER_TOTAL)],
        "layer_volume_labels": [
            volume_label(layer_volume_pct(i)) for i in range(LAYER_TOTAL)
        ],
        "layer_playing": [False] * LAYER_TOTAL,
        "layer_wav_names": [OFF_VALUE] * LAYER_TOTAL,
        "key_index": 0,
        "base_index": BASE_FREQUENCY_INDEX,
        "detune_pct": DETUNE_DEFAULT,
        "lfo_pct": LFO_DEFAULT,
        "richness_pct": RICHNESS_DEFAULT,
        "drone_status": DRONE_OPENING_STATUS,
        "music_files": [],
        "music_row": -1,
        "music_playing": False,
        "music_volume_pct": MUSIC_VOLUME_DEFAULT_PCT,
        "music_button_label": PLAY_LABEL,
        "music_caption": NOTHING_PLAYING_TEXT,
        "waveform_layers": 0,
        "waveform_key": DEFAULT_KEY,
        "waveform_phase": 0.0,
    }


def copied_state(state: dict) -> dict:
    """One state copied deep enough that a step cannot reach the original."""
    return {
        name: list(value) if isinstance(value, list) else value
        for name, value in state.items()
    }


def current_key(state: dict) -> Any:
    """The key the drone engine is set to, or nothing when none is chosen."""
    index = state["key_index"]
    if index < 0 or index >= len(KEY_NAMES):
        return NO_CHOICE
    return KEY_NAMES[index]


def current_base_freq(state: dict) -> Any:
    """The base frequency chosen, or nothing when none is chosen."""
    index = state["base_index"]
    if index < 0 or index >= len(BASE_FREQUENCIES):
        return NO_CHOICE
    return BASE_FREQUENCIES[index][1]


def active_layer_total(state: dict) -> int:
    """How many layers are playing a preset they were given."""
    return sum(
        1
        for index in range(LAYER_TOTAL)
        if state["layer_playing"][index] and bool(state["layer_presets"][index])
    )


def generated(state: dict) -> dict:
    """Build a tone for every layer that has a preset, and word the status.

    A layer with no sound library builds no file, which is the wording
    the status line carries as an error.
    """
    key = current_key(state)
    base = current_base_freq(state)
    started = 0
    errors = []
    reported = False
    for index in range(LAYER_TOTAL):
        preset = state["layer_presets"][index]
        if not preset:
            continue
        started += 1
        if not has_player(state["media"]):
            state["layer_playing"][index] = False
            reported = True
        elif base is not None:
            state["layer_wav_names"][index] = wav_file_name(preset, key)
            state["layer_playing"][index] = True
            reported = True
        if not state["layer_wav_names"][index]:
            errors.append(NO_WAV_FORMAT.format(index + 1))
    if errors:
        state["drone_status"] = drone_error_status(started, errors)
    else:
        state["drone_status"] = drone_status(
            started,
            key,
            state["detune_pct"],
            state["lfo_pct"],
            state["richness_pct"],
            has_music_controls(state["media"]),
        )
    if reported:
        state = reported_to_waveform(state)
    return state


def key_text(key: Any) -> str:
    """The key as the waveform receives it.

    The panel reports the key over a signal declared to carry text, so a
    key that was never chosen arrives as the empty text rather than as
    nothing.
    """
    return key if isinstance(key, str) else NOT_ASKED


def reported_to_waveform(state: dict) -> dict:
    """Hand the playing layer count and the key to the waveform.

    A layer reports itself when it starts and when it stops. A build
    that never reached the layer reports nothing, so the waveform keeps
    what it last heard.
    """
    state["waveform_layers"] = active_layer_total(state)
    state["waveform_key"] = key_text(current_key(state))
    return state


def played(state: dict, index: Any) -> dict:
    """Start one track of the music list, if the list reaches that far."""
    if not has_player(state["media"]) or index >= len(state["music_files"]):
        return state
    state["music_caption"] = now_playing_text(state["music_files"][index])
    state["music_button_label"] = PAUSE_LABEL
    state["music_playing"] = True
    state["music_row"] = index
    return state


def layer_index(index: Any) -> int:
    """One layer position, refusing a value no layer sits at.

    The panel reaches its layers through a list of four, so a position
    outside that list refuses the way the panel refuses, and a position
    counted from the end reaches the same layer.
    """
    return list(range(LAYER_TOTAL))[index]


def layer_step(state: dict, name: str, values: tuple) -> dict:
    """Apply one drone-layer action to `state` and return it.

    The layer is found before its value is read, which is the order the
    panel uses: a position no layer sits at refuses first.
    """
    index = layer_index(values[0])
    if name == "select_preset":
        state["layer_presets"][index] = chosen_preset(values[1])
    elif name == "set_layer_volume":
        held = slider_value(values[1], *VOLUME_RANGE_PCT)
        state["layer_volumes_pct"][index] = held
        state["layer_volume_labels"][index] = volume_label(held)
    elif name == "layer_error":
        state["layer_playing"][index] = False
        state = reported_to_waveform(state)
    return state


def drone_step(state: dict, name: str, values: tuple) -> dict:
    """Apply one drone-engine action to `state` and return it."""
    if name == "set_detune":
        state["detune_pct"] = slider_value(values[0], *DETUNE_RANGE)
    elif name == "set_lfo":
        state["lfo_pct"] = slider_value(values[0], *LFO_RANGE)
    elif name == "set_richness":
        state["richness_pct"] = slider_value(values[0], *RICHNESS_RANGE)
    elif name == "select_key":
        state["key_index"] = key_index_for(values[0])
    elif name == "select_base":
        state["base_index"] = base_index_for(values[0])
    elif name == "generate_all":
        state = generated(state)
    elif name == "stop_all":
        state["layer_playing"] = [False] * LAYER_TOTAL
        state["drone_status"] = STOPPED_TEXT
        state = reported_to_waveform(state)
    elif name == "key_up":
        state["key_index"] = next_key_index(state["key_index"])
        state["drone_status"] = SHIFTING_FORMAT.format(current_key(state))
        state = generated(state)
    return state


def music_step(state: dict, name: str, values: tuple) -> dict:
    """Apply one music-player action to `state` and return it."""
    if name == "add_files":
        for path in values[0]:
            state["music_files"].append(path)
            missing_control(state["media"], "list")
    elif name == "play_index":
        state = played(state, values[0])
    elif name == "toggle_music":
        state = toggled(state)
    elif name in ("next_track", "music_ended"):
        if state["music_files"]:
            missing_control(state["media"], "list")
            state = played(state, (state["music_row"] + 1) % len(state["music_files"]))
    elif name == "stop_music":
        missing_control(state["media"], "play button")
        state["music_button_label"] = PLAY_LABEL
        state["music_playing"] = False
    elif name == "set_music_volume":
        missing_control(state["media"], "volume slider")
        state["music_volume_pct"] = slider_value(values[0], *VOLUME_RANGE_PCT)
    return state


def waveform_step(state: dict, name: str, values: tuple) -> dict:
    """Apply one waveform action to `state` and return it."""
    if name == "animate" and state["waveform_layers"] > 0:
        state["waveform_phase"] += values[0] * ANIMATION_PHASE_GAIN
    return state


def toggled(state: dict) -> dict:
    """Pause the playing track, or start the chosen one.

    Without the sound library the button reaches no player, so the state
    is handed back unchanged.
    """
    if not has_player(state["media"]):
        return state
    if state["music_playing"]:
        state["music_button_label"] = PLAY_LABEL
        state["music_playing"] = False
    elif state["music_files"]:
        state = played(state, max(0, state["music_row"]))
    return state


def stepped(state: dict, name: Any, values: tuple) -> dict:
    """Apply one named action to `state` where it stands and return it.

    Raises UnknownStep for a name this surface does not run, and lets a
    step's own refusal through for a value it cannot use. A refusal part
    way leaves what the step had already done.
    """
    if name in LAYER_STEPS:
        handler = layer_step
    elif name in DRONE_STEPS:
        handler = drone_step
    elif name in MUSIC_STEPS:
        handler = music_step
    elif name in WAVEFORM_STEPS:
        handler = waveform_step
    else:
        raise UnknownStep(name)
    return handler(state, name, values)


def apply_step(state: dict, name: Any, args: Any = ()) -> dict:
    """Return the state after one named screen action.

    The state handed in is copied first, so a caller keeps the state it
    passed whatever the step does.
    """
    return stepped(copied_state(state), name, tuple(args))


def run_steps(steps: Any, media: Any = MEDIA_READY) -> dict:
    """Run a sequence of named steps and report where it stopped.

    Every step that ran is listed with its index, its name and the state
    it left. A step that refuses stops the sequence and is reported by
    index, by name and by the kind of refusal, never by its wording.
    """
    state = initial_state(media)
    done: list[dict] = []
    for index, step in enumerate(steps):
        name = step[0]
        args = step[1] if len(step) > 1 else ()
        try:
            state = stepped(state, name, tuple(args))
        except UnknownStep:
            return {
                "stopped_at_index": index,
                "stopped_at_step": name,
                "refusal": UNKNOWN_STEP_REFUSAL,
                "steps_done": done,
                "state": state,
            }
        except Exception as refused:
            return {
                "stopped_at_index": index,
                "stopped_at_step": name,
                "refusal": type(refused).__name__,
                "steps_done": done,
                "state": state,
            }
        done.append({"index": index, "step": name, "state": copied_state(state)})
    return {
        "stopped_at_index": NOT_STOPPED,
        "stopped_at_step": NOT_ASKED,
        "refusal": NO_REFUSAL,
        "steps_done": done,
        "state": state,
    }


def requested_name(name: Any) -> str:
    """The name a caller asked for, and the empty string for anything else."""
    return name if isinstance(name, str) else NOT_ASKED


def preset_answer(name: Any) -> tuple[list, str]:
    """One preset's pairs, and the refusal text when there are none."""
    try:
        return [list(pair) for pair in preset_intervals(name)], NOT_ASKED
    except TypeError as refused:
        return [], str(refused)


def key_answer(name: Any) -> tuple[float, str]:
    """One key's multiplier, and the refusal text when there is none."""
    try:
        return key_multiplier(name), NOT_ASKED
    except TypeError as refused:
        return 0.0, str(refused)


def build_view_model(
    preset: Any = None,
    key: Any = None,
    steps: Any = None,
    media: Any = MEDIA_READY,
) -> dict:
    """Return every table the audio tab paints from, and one request's answers.

    `preset` and `key` carry the names a caller asked for. A name no
    table holds comes back under `unknown_preset` or `unknown_key` with
    the fallback beside it. `steps` is a sequence of screen actions run
    over a fresh state; the answer names where the sequence stopped.
    """
    asked_preset = requested_name(preset)
    asked_key = requested_name(key)
    intervals, preset_refusal = preset_answer(asked_preset)
    multiplier, key_refusal = key_answer(asked_key)
    return {
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "channel_total": CHANNEL_TOTAL,
        "sample_width_bytes": SAMPLE_WIDTH_BYTES,
        "bytes_per_frame": BYTES_PER_FRAME,
        "full_scale": FULL_SCALE,
        "crossfade_s": CROSSFADE_S,
        "crossfade_blend": CROSSFADE_BLEND,
        "default_duration_s": DEFAULT_DURATION_S,
        "generate_volume": GENERATE_VOLUME,
        "richness_floor": RICHNESS_FLOOR,
        "richness_gain": RICHNESS_GAIN,
        "detune_depth": DETUNE_DEPTH,
        "detune_rate_hz": DETUNE_RATE_HZ,
        "frequency_phase": FREQUENCY_PHASE,
        "lfo_depth": LFO_DEPTH,
        "lfo_rate_hz": LFO_RATE_HZ,
        "key_multipliers": dict(KEY_MULTIPLIERS),
        "key_names": list(KEY_NAMES),
        "default_key": DEFAULT_KEY,
        "presets": {name: [list(p) for p in rows] for name, rows in PRESETS.items()},
        "preset_names": list(PRESET_NAMES),
        "fallback_preset": FALLBACK_PRESET,
        "off_label": OFF_LABEL,
        "off_value": OFF_VALUE,
        "layer_total": LAYER_TOTAL,
        "first_layer_volume_pct": FIRST_LAYER_VOLUME_PCT,
        "other_layer_volume_pct": OTHER_LAYER_VOLUME_PCT,
        "volume_range_pct": list(VOLUME_RANGE_PCT),
        "volume_label_width_px": VOLUME_LABEL_WIDTH_PX,
        "base_frequencies": [list(row) for row in BASE_FREQUENCIES],
        "base_frequency_index": BASE_FREQUENCY_INDEX,
        "detune_range": list(DETUNE_RANGE),
        "detune_default": DETUNE_DEFAULT,
        "detune_divisor": DETUNE_DIVISOR,
        "detune_tooltip": DETUNE_TOOLTIP,
        "lfo_range": list(LFO_RANGE),
        "lfo_default": LFO_DEFAULT,
        "lfo_divisor": LFO_DIVISOR,
        "lfo_tooltip": LFO_TOOLTIP,
        "richness_range": list(RICHNESS_RANGE),
        "richness_default": RICHNESS_DEFAULT,
        "richness_divisor": RICHNESS_DIVISOR,
        "richness_tooltip": RICHNESS_TOOLTIP,
        "music_title": MUSIC_TITLE,
        "drone_title": DRONE_TITLE,
        "music_button_labels": list(MUSIC_BUTTON_LABELS),
        "drone_button_labels": list(DRONE_BUTTON_LABELS),
        "key_up_tooltip": KEY_UP_TOOLTIP,
        "control_labels": dict(CONTROL_LABELS),
        "play_label": PLAY_LABEL,
        "pause_label": PAUSE_LABEL,
        "nothing_playing_text": NOTHING_PLAYING_TEXT,
        "now_playing_format": NOW_PLAYING_FORMAT,
        "music_list_max_height_px": MUSIC_LIST_MAX_HEIGHT_PX,
        "music_volume_default_pct": MUSIC_VOLUME_DEFAULT_PCT,
        "file_dialog_title": FILE_DIALOG_TITLE,
        "file_dialog_filter": FILE_DIALOG_FILTER,
        "media_missing_text": MEDIA_MISSING_TEXT,
        "drone_opening_status": DRONE_OPENING_STATUS,
        "generating_text": GENERATING_TEXT,
        "stopped_text": STOPPED_TEXT,
        "shifting_format": SHIFTING_FORMAT,
        "layer_label_format": LAYER_LABEL_FORMAT,
        "volume_label_format": VOLUME_LABEL_FORMAT,
        "no_wav_format": NO_WAV_FORMAT,
        "drone_error_format": DRONE_ERROR_FORMAT,
        "drone_playing_format": DRONE_PLAYING_FORMAT,
        "media_present_text": MEDIA_PRESENT_TEXT,
        "media_absent_text": MEDIA_ABSENT_TEXT,
        "wav_name_format": WAV_NAME_FORMAT,
        "wav_directory_source": WAV_DIRECTORY_SOURCE,
        "preset_name_space": PRESET_NAME_SPACE,
        "preset_name_space_replacement": PRESET_NAME_SPACE_REPLACEMENT,
        "preset_name_sharp": PRESET_NAME_SHARP,
        "preset_name_sharp_replacement": PRESET_NAME_SHARP_REPLACEMENT,
        "waveform_min_height_px": WAVEFORM_MIN_HEIGHT_PX,
        "waveform_max_height_px": WAVEFORM_MAX_HEIGHT_PX,
        "waveform_idle_text": WAVEFORM_IDLE_TEXT,
        "waveform_key_format": WAVEFORM_KEY_FORMAT,
        "waveform_background_top": WAVEFORM_BACKGROUND_TOP,
        "waveform_background_bottom": WAVEFORM_BACKGROUND_BOTTOM,
        "waveform_idle_colour": WAVEFORM_IDLE_COLOUR,
        "waveform_key_colour": WAVEFORM_KEY_COLOUR,
        "waveform_idle_font": list(WAVEFORM_IDLE_FONT),
        "waveform_key_font": list(WAVEFORM_KEY_FONT),
        "waveform_key_inset_px": WAVEFORM_KEY_INSET_PX,
        "waveform_key_baseline_px": WAVEFORM_KEY_BASELINE_PX,
        "layer_trace_colours": list(LAYER_TRACE_COLOURS),
        "layer_trace_alpha": LAYER_TRACE_ALPHA,
        "layer_trace_width_px": LAYER_TRACE_WIDTH_PX,
        "layer_trace_step_px": LAYER_TRACE_STEP_PX,
        "trace_amplitude_base_px": TRACE_AMPLITUDE_BASE_PX,
        "trace_amplitude_step_px": TRACE_AMPLITUDE_STEP_PX,
        "trace_cycles": TRACE_CYCLES,
        "trace_rate_base": TRACE_RATE_BASE,
        "trace_rate_step": TRACE_RATE_STEP,
        "trace_phase_step": TRACE_PHASE_STEP,
        "animation_step_s": ANIMATION_STEP_S,
        "animation_phase_gain": ANIMATION_PHASE_GAIN,
        "splitter_sizes_px": list(SPLITTER_SIZES_PX),
        "splitter_handle_width_px": SPLITTER_HANDLE_WIDTH_PX,
        "splitter_children_collapsible": SPLITTER_CHILDREN_COLLAPSIBLE,
        "tab_margins_px": list(TAB_MARGINS_PX),
        "tab_spacing_px": TAB_SPACING_PX,
        "accessible_names": dict(ACCESSIBLE_NAMES),
        "skin": dict(SKIN),
        "equal_channel_colours": list(EQUAL_CHANNEL_COLOURS),
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "signals": list(SIGNALS),
        "thread_total": THREAD_TOTAL,
        "step_names": list(STEP_NAMES),
        "layer_steps": list(LAYER_STEPS),
        "drone_steps": list(DRONE_STEPS),
        "music_steps": list(MUSIC_STEPS),
        "waveform_steps": list(WAVEFORM_STEPS),
        "media_states": list(MEDIA_STATES),
        "slider_min": SLIDER_MIN,
        "slider_max": SLIDER_MAX,
        "nothing_chosen_index": NOTHING_CHOSEN_INDEX,
        "missing_control_format": MISSING_CONTROL_FORMAT,
        "requested_media": media,
        "requested_preset": asked_preset,
        "requested_key": asked_key,
        "preset_intervals": intervals,
        "preset_refusal": preset_refusal,
        "key_multiplier": multiplier,
        "key_refusal": key_refusal,
        "unknown_preset": [] if has_preset(asked_preset) else [asked_preset],
        "unknown_key": [] if has_key(asked_key) else [asked_key],
        "wav_file_name": wav_file_name(
            asked_preset if has_preset(asked_preset) else FALLBACK_PRESET,
            asked_key if has_key(asked_key) else DEFAULT_KEY,
        ),
        "run": run_steps(steps or (), media),
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``audio_suite.state``.

    Reads ``preset``, ``key``, ``steps`` and ``media`` from the request
    parameters. Every table is the same on every call, so there is no
    state to reset.
    """
    return build_view_model(
        params.get("preset"),
        params.get("key"),
        params.get("steps"),
        params.get("media", MEDIA_READY),
    )
