"""The waveform the shipped widget paints, against the surface's own.

A failure means the surface carries a different colour, a different
font, a different trace or a different caption than
``src.gui.audio_suite.WaveformWidget`` paints.

One render comes from the shipped widget and one from a widget built
only from the surface's payload. Two renders of the same side would
measure the host's fonts rather than the product.
"""

from __future__ import annotations

import math
import os
from contextlib import contextmanager

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui import audio_suite as shipped
from src.gui.main_tabs import audio_suite_surface as surface
from tests.fixtures.host_fonts import (
    NARROW_LABEL,
    WIDE_LABEL,
    app_font_advance_px,
    skip_unless_no_fonts,
    skip_unless_real_fonts,
)
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
    sealed,
    unaltered,
)

# The waveform holds itself between fifty and seventy pixels tall, so a
# render is asked for a height inside that. The width is the panel's.
PICTURE_SIZE = (700, 64)

# One state is one thing the waveform can be showing.
PICTURE_CASES = {
    "idle": (0, "C"),
    "one_layer": (1, "C"),
    "two_layers": (2, "A#"),
    "three_layers": (3, "F#"),
    "four_layers": (4, "B"),
    "more_layers_than_traces": (9, "G"),
    "no_key_chosen": (2, ""),
}

# A rule neither side sets, used to prove a render carries what a widget
# was told to paint.
NO_SKIN_RULE = "QWidget { background: #ff00ff; }"

NO_SKIN_COLOUR = "#ff00ff"

FLAT_COLOUR_TOTAL = 1


def app():
    """The process application object every render needs."""
    from tests.qt_pixel import ensure_app

    return ensure_app()


def render(widget):
    """One render of a widget at the one size both sides are asked for."""
    from tests.qt_pixel import render_widget

    return render_widget(widget, PICTURE_SIZE)


def colour_total(image):
    """How many different colours one render painted."""
    from PySide6.QtGui import QColor

    seen = set()
    for x in range(0, image.width(), 3):
        for y in range(0, image.height(), 3):
            seen.add(QColor(image.pixelColor(x, y)).name())
    return len(seen)


def skin_colour(name):
    """The one colour a style rule names."""
    for part in surface.SKIN[name].replace(";", " ").replace(":", " ").split():
        if part.startswith("#"):
            return part
    raise AssertionError("%s names no colour: %r" % (name, surface.SKIN[name]))


def repeats_a_channel(colour):
    """Whether a colour carries the same number in two of its channels.

    A three-digit colour is the six-digit one with every digit doubled,
    so its channels always match. A swap of two matching channels paints
    the very same pixel, which no render can report.
    """
    digits = colour.lstrip("#")
    if len(digits) == 3:
        digits = "".join(digit * 2 for digit in digits)
    return len({digits[0:2], digits[2:4], digits[4:6]}) < 3


def shipped_waveform(layers, key):
    """The real waveform widget, told what to show and nothing more."""
    app()
    widget = shipped.WaveformWidget()
    widget.set_state(layers, key)
    return widget


def waveform_payload(layers, key):
    """Every value a waveform render needs, taken off the surface."""
    return sealed(
        {
            "layers": layers,
            "key": key,
            "phase": 0.0,
            "min_height_px": surface.WAVEFORM_MIN_HEIGHT_PX,
            "max_height_px": surface.WAVEFORM_MAX_HEIGHT_PX,
            "background_top": surface.WAVEFORM_BACKGROUND_TOP,
            "background_bottom": surface.WAVEFORM_BACKGROUND_BOTTOM,
            "idle_text": surface.WAVEFORM_IDLE_TEXT,
            "idle_colour": surface.WAVEFORM_IDLE_COLOUR,
            "idle_font": list(surface.WAVEFORM_IDLE_FONT),
            "key_format": surface.WAVEFORM_KEY_FORMAT,
            "key_colour": surface.WAVEFORM_KEY_COLOUR,
            "key_font": list(surface.WAVEFORM_KEY_FONT),
            "key_inset_px": surface.WAVEFORM_KEY_INSET_PX,
            "key_baseline_px": surface.WAVEFORM_KEY_BASELINE_PX,
            "trace_colours": list(surface.LAYER_TRACE_COLOURS),
            "trace_alpha": surface.LAYER_TRACE_ALPHA,
            "trace_width_px": surface.LAYER_TRACE_WIDTH_PX,
            "trace_step_px": surface.LAYER_TRACE_STEP_PX,
            "amplitude_base_px": surface.TRACE_AMPLITUDE_BASE_PX,
            "amplitude_step_px": surface.TRACE_AMPLITUDE_STEP_PX,
            "cycles": surface.TRACE_CYCLES,
            "rate_base": surface.TRACE_RATE_BASE,
            "rate_step": surface.TRACE_RATE_STEP,
            "phase_step": surface.TRACE_PHASE_STEP,
        }
    )


def waveform_from_payload(payload):
    """A widget painting one waveform from the payload, and from nothing else."""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
    from PySide6.QtWidgets import QWidget

    unaltered(payload)
    app()

    class PayloadWaveform(QWidget):
        def __init__(self, values):
            super().__init__()
            self._values = values
            self.setAccessibleName("Waveform Widget")
            self.setMinimumHeight(values["min_height_px"])
            self.setMaximumHeight(values["max_height_px"])

        def paintEvent(self, _event):
            values = self._values
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            width, height = self.width(), self.height()
            ground = QLinearGradient(0, 0, 0, height)
            ground.setColorAt(0, QColor(values["background_top"]))
            ground.setColorAt(1, QColor(values["background_bottom"]))
            painter.fillRect(0, 0, width, height, ground)
            if values["layers"] == 0:
                painter.setPen(QPen(QColor(values["idle_colour"])))
                painter.setFont(QFont(*values["idle_font"]))
                painter.drawText(
                    QRectF(0, 0, width, height), Qt.AlignCenter, values["idle_text"]
                )
                painter.end()
                return
            middle = height / 2
            colours = values["trace_colours"]
            for trace in range(min(values["layers"], len(colours))):
                colour = QColor(colours[trace])
                colour.setAlpha(values["trace_alpha"])
                painter.setPen(QPen(colour, values["trace_width_px"]))
                previous = None
                for across in range(0, width, values["trace_step_px"]):
                    moment = values["phase"] + across / width * values["cycles"]
                    down = middle + (
                        values["amplitude_base_px"]
                        + trace * values["amplitude_step_px"]
                    ) * math.sin(
                        2
                        * math.pi
                        * (values["rate_base"] + trace * values["rate_step"])
                        * moment
                        + trace * values["phase_step"]
                    )
                    if previous:
                        painter.drawLine(previous[0], previous[1], across, int(down))
                    previous = (across, int(down))
            painter.setPen(QPen(QColor(values["key_colour"])))
            painter.setFont(QFont(*values["key_font"]))
            painter.drawText(
                width - values["key_inset_px"],
                int(middle + values["key_baseline_px"]),
                values["key_format"].format(values["key"]),
            )
            painter.end()

    return PayloadWaveform(payload)


def flat_widget():
    """A widget carrying a rule neither side sets, so it paints one colour."""
    from PySide6.QtWidgets import QWidget

    app()
    widget = QWidget()
    widget.setStyleSheet(NO_SKIN_RULE)
    return widget


@pytest.mark.parametrize("case", sorted(PICTURE_CASES))
def test_the_two_sides_paint_one_waveform(case):
    """The surface painted a different waveform than the shipped widget."""
    layers, key = PICTURE_CASES[case]
    assert_pictures_match(
        old_side=render(shipped_waveform(layers, key)),
        new_side=render(waveform_from_payload(waveform_payload(layers, key))),
        note="%s layers in %r" % (layers, key),
    )


def test_the_picture_comparison_can_report_a_difference():
    """The picture check passes whatever the second side paints.

    Two real states, one taken from each side. A pass proves the
    comparison reports a waveform painted differently, so the matches
    above are not green by being unable to fail.
    """
    assert_pictures_differ(
        old_side=render(shipped_waveform(0, "C")),
        new_side=render(waveform_from_payload(waveform_payload(4, "B"))),
        note="idle against four layers",
    )
    assert_pictures_differ(
        old_side=render(shipped_waveform(4, "B")),
        new_side=render(waveform_from_payload(waveform_payload(0, "C"))),
        note="four layers against idle",
    )


@pytest.mark.parametrize("case", sorted(PICTURE_CASES))
def test_the_painted_waveform_shows_more_than_one_colour(case):
    """The two sides matched because the waveform painted one flat colour."""
    layers, key = PICTURE_CASES[case]
    image = render(waveform_from_payload(waveform_payload(layers, key)))
    assert image.width() == PICTURE_SIZE[0]
    assert image.height() == PICTURE_SIZE[1]
    found = colour_total(image)
    assert found > FLAT_COLOUR_TOTAL, "%s painted %d colour" % (case, found)


def test_a_window_that_paints_one_colour_is_told_from_one_that_does_not():
    """The colour counter reports the same number whatever it is shown.

    A widget carrying a rule neither side sets paints one flat colour. A
    counter that cannot tell it from the product's own render would make
    every count above meaningless.
    """
    from PySide6.QtGui import QColor

    flat = render(flat_widget())
    assert colour_total(flat) == FLAT_COLOUR_TOTAL, colour_total(flat)
    assert QColor(flat.pixelColor(10, 10)).name() == NO_SKIN_COLOUR
    painted = render(shipped_waveform(4, "B"))
    assert colour_total(painted) > FLAT_COLOUR_TOTAL, colour_total(painted)
    assert_pictures_differ(old_side=painted, new_side=flat, note="painted against flat")


def test_the_two_sides_hold_the_waveform_to_one_height():
    """The waveform grew or shrank on one side only."""
    old = shipped_waveform(0, "C")
    new = waveform_from_payload(waveform_payload(0, "C"))
    assert old.minimumHeight() == surface.WAVEFORM_MIN_HEIGHT_PX
    assert old.maximumHeight() == surface.WAVEFORM_MAX_HEIGHT_PX
    assert new.minimumHeight() == old.minimumHeight()
    assert new.maximumHeight() == old.maximumHeight()
    assert old.accessibleName() == surface.ACCESSIBLE_NAMES["waveform"]


def test_the_seal_refuses_a_payload_that_was_changed():
    """A render of a changed payload measures the host, not the product."""
    payload = waveform_payload(2, "A#")
    payload["key_colour"] = "#ff0000"
    with pytest.raises(AssertionError):
        waveform_from_payload(payload)


def test_the_seal_takes_a_payload_that_was_not_changed():
    """The seal refuses every payload, so the refusal above proves nothing."""
    payload = waveform_payload(2, "A#")
    assert waveform_from_payload(payload) is not None


# The values no render of this waveform can report, each with the check
# that does cover it.
BLIND_TO_THE_PICTURE = {
    "equal_channel_colours": "test_the_equal_channel_colours_are_compared_as_text",
    "key_font_is_fixed_width": "test_the_key_caption_is_painted_in_a_fixed_width_font",
    "layer_and_music_skin": (
        "test_the_skin_the_waveform_never_paints_is_shown_by_its_own_render"
    ),
    "trace_colours_past_the_fourth": ("test_a_fifth_layer_paints_no_trace_of_its_own"),
}


def test_the_equal_channel_colours_are_compared_as_text():
    """A colour whose channels match had two of them swapped.

    Six colours in this tab carry the same number in two channels or in
    all three, so swapping those two paints the very same pixel. Each is
    read off the surface as text instead.
    """
    named = {
        "waveform_background_top": surface.WAVEFORM_BACKGROUND_TOP,
        "waveform_background_bottom": surface.WAVEFORM_BACKGROUND_BOTTOM,
        "waveform_idle_colour": surface.WAVEFORM_IDLE_COLOUR,
        "waveform_key_colour": surface.WAVEFORM_KEY_COLOUR,
        "drone_status": skin_colour("drone_status"),
        "layer_frame": skin_colour("layer_frame"),
        "music_now_playing": skin_colour("music_now_playing"),
        "drone_play_all_button": skin_colour("drone_play_all_button"),
    }
    found = [name for name, value in named.items() if repeats_a_channel(value)]
    assert sorted(found) == sorted(surface.EQUAL_CHANNEL_COLOURS), found
    assert repeats_a_channel("#888") is True
    assert repeats_a_channel("#00ccff") is False
    assert surface.WAVEFORM_BACKGROUND_TOP == "#08080e"
    assert surface.WAVEFORM_IDLE_COLOUR == "#323246"
    assert "#888" in surface.SKIN["drone_status"]
    assert "#333333" in surface.SKIN["layer_frame"]
    for colour in surface.LAYER_TRACE_COLOURS:
        assert len({colour[1:3], colour[3:5], colour[5:7]}) == 3, colour


def test_the_key_caption_is_painted_in_a_fixed_width_font():
    """The caption font gained a width of its own, so a picture could see it.

    Every letter of a fixed-width font takes the same room, so two
    captions of one length paint the same shape whatever they say. The
    font is read as text instead.
    """
    from PySide6.QtGui import QFont, QFontMetrics

    app()
    assert surface.WAVEFORM_KEY_FONT == ("Consolas", 8)
    assert surface.WAVEFORM_IDLE_FONT == ("Segoe UI", 9)
    metrics = QFontMetrics(QFont(*surface.WAVEFORM_KEY_FONT))
    assert metrics.horizontalAdvance(NARROW_LABEL) == metrics.horizontalAdvance(
        WIDE_LABEL
    ), "the caption font gives its glyphs their own widths"
    assert surface.WAVEFORM_KEY_FORMAT.format("C") == "Key: C"
    assert surface.WAVEFORM_KEY_FORMAT.format("A#") == "Key: A#"


def test_the_skin_the_waveform_never_paints_is_shown_by_its_own_render():
    """A style sheet no waveform render can show was left to that render.

    The layer frame, the play button, the caption and the status line
    are painted by other widgets, so each is compared by its own render
    below rather than by the waveform's.
    """
    covered = {
        "layer_frame": "test_the_layer_frame_paints_the_border_the_surface_names",
        "music_play_button": "test_the_play_button_paints_what_the_surface_names",
        "music_now_playing": "test_the_caption_paints_what_the_surface_names",
        "drone_status": "test_the_status_line_paints_what_the_surface_names",
    }
    for name, covered_by in covered.items():
        assert surface.SKIN[name].strip(), name
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by
    assert set(covered) | {"drone_play_all_button"} == set(surface.SKIN)


class SilentSignal:
    """A signal a stand-in player carries, so a wiring can be made."""

    def connect(self, _slot):
        """Keep nothing. The panels only need the wiring to succeed."""


class SilentOutput:
    """An audio output that opens no device."""

    def setVolume(self, _value):
        """Take the volume and do nothing with it."""


class SilentPlayer:
    """A media player that plays nothing."""

    def __init__(self):
        self.mediaStatusChanged = SilentSignal()
        self.errorOccurred = SilentSignal()
        self.playbackStateChanged = SilentSignal()

    def setAudioOutput(self, _output):
        """Take the output and do nothing with it."""


@contextmanager
def no_sound():
    """Build the shipped panels with every control and no device.

    The library stays present, so the music panel builds its list, its
    buttons and its caption. Only the player and the output are stood in
    for, and both are put back afterwards.
    """
    was_media = shipped._HAS_MEDIA
    was_output = shipped.QAudioOutput
    was_player = shipped.QMediaPlayer
    shipped._HAS_MEDIA = True
    shipped.QAudioOutput = SilentOutput
    shipped.QMediaPlayer = SilentPlayer
    try:
        yield
    finally:
        shipped._HAS_MEDIA = was_media
        shipped.QAudioOutput = was_output
        shipped.QMediaPlayer = was_player


def styled_frame(rule):
    """A bare frame carrying one style rule and nothing else."""
    from PySide6.QtWidgets import QFrame

    app()
    frame = QFrame()
    frame.setFrameShape(QFrame.StyledPanel)
    frame.setStyleSheet(rule)
    return frame


def styled_label(text, rule, wrap=False):
    """A bare label carrying one text and one style rule."""
    from PySide6.QtWidgets import QLabel

    app()
    label = QLabel(text)
    label.setStyleSheet(rule)
    label.setWordWrap(wrap)
    return label


def styled_button(text, rule):
    """A bare button carrying one text and one style rule."""
    from PySide6.QtWidgets import QPushButton

    app()
    button = QPushButton(text)
    button.setStyleSheet(rule)
    return button


def test_the_layer_frame_paints_the_border_the_surface_names():
    """The layer border is painted a different colour than the surface names.

    Both colours are read off a render, never off a live widget: a
    declared colour is not the painted one.
    """
    from PySide6.QtGui import QColor

    app()
    with no_sound():
        old = render(styled_frame(shipped.DroneLayer(0).styleSheet()))
    new = render(styled_frame(surface.SKIN["layer_frame"]))
    assert_pictures_match(old_side=old, new_side=new, note="layer frame")
    edge = QColor(new.pixelColor(0, PICTURE_SIZE[1] // 2)).name()
    middle = QColor(new.pixelColor(PICTURE_SIZE[0] // 2, PICTURE_SIZE[1] // 2)).name()
    assert edge != middle, (edge, middle)
    assert edge == "#333333", edge


def test_the_caption_paints_what_the_surface_names():
    """The caption under the music list is painted differently."""
    with no_sound():
        panel = shipped.MusicPlayerPanel()
        rule = panel._now.styleSheet()
        text = panel._now.text()
    old = render(styled_label(text, rule))
    new = render(
        styled_label(surface.NOTHING_PLAYING_TEXT, surface.SKIN["music_now_playing"])
    )
    assert_pictures_match(old_side=old, new_side=new, note="now playing caption")
    assert colour_total(new) > FLAT_COLOUR_TOTAL, colour_total(new)


def test_the_status_line_paints_what_the_surface_names():
    """The line under the drone engine is painted differently."""
    with no_sound():
        panel = shipped.DroneEnginePanel()
        rule = panel._st.styleSheet()
        text = panel._st.text()
        wrap = panel._st.wordWrap()
    old = render(styled_label(text, rule, wrap=wrap))
    new = render(
        styled_label(
            surface.DRONE_OPENING_STATUS, surface.SKIN["drone_status"], wrap=wrap
        )
    )
    assert_pictures_match(old_side=old, new_side=new, note="drone status line")


def test_the_play_button_paints_what_the_surface_names():
    """The play button is painted differently on the two sides."""
    with no_sound():
        panel = shipped.MusicPlayerPanel()
        rule = panel._pb.styleSheet()
        assert panel._pb.text() == surface.PLAY_LABEL
    old = render(styled_button(surface.PLAY_LABEL, rule))
    new = render(styled_button(surface.PLAY_LABEL, surface.SKIN["music_play_button"]))
    assert_pictures_match(old_side=old, new_side=new, note="play button")
    assert_pictures_differ(
        old_side=new,
        new_side=render(styled_button(surface.PLAY_LABEL, NO_SKIN_RULE)),
        note="the play button against a rule neither side sets",
    )


def test_a_bold_weight_reaches_no_pixel_where_the_host_ships_no_fonts():
    """A host with no fonts painted a bold glyph, or one with fonts did not.

    Measured on this repository: with no font database every family
    resolves to one box font that has no heavier form, so the play
    button's only rule moves no pixel. Where the host ships fonts it
    does. The host is asked rather than assumed, and both answers are
    checked.
    """
    from tests.fixtures.host_fonts import has_real_fonts, load_run_fonts

    app()
    load_run_fonts()
    bold = render(styled_button(surface.PLAY_LABEL, surface.SKIN["music_play_button"]))
    plain = render(styled_button(surface.PLAY_LABEL, ""))
    if has_real_fonts():
        assert_pictures_differ(old_side=bold, new_side=plain, note="fonts present")
    else:
        assert_pictures_match(old_side=bold, new_side=plain, note="no fonts")
    assert surface.SKIN["music_play_button"] == "font-weight:bold;"


def test_the_skin_comparison_can_report_a_difference():
    """The skin renders match whatever rule the second side carries."""
    assert_pictures_differ(
        old_side=render(styled_frame(surface.SKIN["layer_frame"])),
        new_side=render(styled_frame(NO_SKIN_RULE)),
        note="layer frame against a rule neither side sets",
    )
    assert_pictures_differ(
        old_side=render(
            styled_label(surface.NOTHING_PLAYING_TEXT, surface.SKIN["drone_status"])
        ),
        new_side=render(
            styled_label(
                surface.NOTHING_PLAYING_TEXT, surface.SKIN["music_now_playing"]
            )
        ),
        note="two real rules, one from each panel",
    )


def test_a_fifth_layer_paints_no_trace_of_its_own():
    """A fifth layer painted a trace the colour table does not hold."""
    assert len(surface.LAYER_TRACE_COLOURS) == 4
    four = render(waveform_from_payload(waveform_payload(4, "G")))
    nine = render(waveform_from_payload(waveform_payload(9, "G")))
    assert_pictures_match(old_side=four, new_side=nine, note="four against nine")
    assert_pictures_match(
        old_side=render(shipped_waveform(9, "G")),
        new_side=nine,
        note="nine layers",
    )


def test_everything_a_picture_cannot_see_is_named_and_covered():
    """A value no render can report was left to the render to report."""
    assert len(BLIND_TO_THE_PICTURE) == 4
    for covered_by in BLIND_TO_THE_PICTURE.values():
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by


@skip_unless_no_fonts
def test_two_captions_of_equal_length_measure_alike_with_no_fonts():
    """The host reports no fonts and the glyphs still have their own widths."""
    app()
    assert len(NARROW_LABEL) == len(WIDE_LABEL)
    assert app_font_advance_px(NARROW_LABEL) == app_font_advance_px(WIDE_LABEL)


@skip_unless_real_fonts
def test_two_captions_of_equal_length_measure_apart_with_real_fonts():
    """The host reports fonts and every glyph still has one width."""
    app()
    assert len(NARROW_LABEL) == len(WIDE_LABEL)
    assert app_font_advance_px(NARROW_LABEL) < app_font_advance_px(WIDE_LABEL)
