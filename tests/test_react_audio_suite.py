"""The React side of the Audio Suite tab.

WHAT IS PROVED
==============
``src/gui/web/audio_suite.js`` draws the waveform strip, the music
player and the ambient drone engine from the payload
``src/gui/main_tabs/audio_suite_surface.py`` serves, and carries no
colour, wording or measurement of its own. The one value the module
works out for itself is the alpha SHARE: the payload carries Qt's
0-to-255 byte, a browser clamps anything above 1 to fully opaque, and a
byte handed straight to CSS paints the waveform traces solid.

The Qt tab this module replaces is NOT removed. The last section builds
the shipped ``AudioSuiteTab`` and counts its live Qt children, so a
deletion of the widget, of a drone layer or of the waveform is reported
here rather than discovered on the operator's screen.

HOW THE JAVASCRIPT IS RUN
=========================
Node is not installed and nothing here adds a JavaScript test runner.
``QJSEngine`` from ``PySide6.QtQml`` runs the module as plain JavaScript
and answers in JSON, through ``tests/fixtures/web_js_modules.py``.

THE CONTROLS
============
Every count has a planted opposite. A field dropped from the payload is
named as a fault. A colour, a surface value, a number and a regular
expression planted in the source are each named by the literal scan. The
alpha check is paired with the byte it refuses. The Qt count is paired
with a tree the check must reject.
"""

from __future__ import annotations

import collections
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

pytest.importorskip("PySide6")

from src.core import desktop_bridge
from src.gui.color_alpha import css_alpha
from src.gui.main_tabs import audio_suite_surface as surface
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    load_order,
    new_engine,
    runs_after,
)

MODULE_NAME = "audio_suite.js"
MODULE_PATH = REPO_ROOT / "src" / "gui" / "web" / MODULE_NAME

MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")
MODULE_LITERALS = js_literals(MODULE_SOURCE)

#: The width the strip is drawn at. Any width answers the same shape;
#: this one divides by the trace step so the point count is exact.
STRIP_WIDTH_PX = 700

#: CSS paints an alpha above this fully opaque, with no error.
CSS_ALPHA_CEILING = 1

#: Every number the module writes, and what it is. A number outside this
#: table is a value the surface should own.
ALGORITHM_NUMBERS = {
    "0",  # the first index of a list, and the left edge of a trace
    "1",  # one step along a list, and the play-all button's position
    "2",  # the two hex digits of a channel, and the library-missing state
    "3",  # the three colour channels, and the digits of a short colour
    "16",  # the radix a hex colour is read in
    "0.5",  # the middle of the strip
    "255",  # the scale Qt's alpha byte runs to
}


def bridge_payload(**params: Any) -> dict:
    """The surface's answer after one round trip through the bridge's JSON.

    ``src/core/desktop_bridge.py`` writes every response with
    ``json.dumps``, so a tuple reaches the renderer as an array.
    Comparing the module against the raw Python dict would charge the
    module for that conversion.
    """
    return json.loads(json.dumps(surface.view_model(params), ensure_ascii=True))


def payload_with_layers(count: int, key: str) -> dict:
    """The payload after enough steps to leave `count` layers sounding."""
    steps: list = [("select_key", (key,))]
    for at in range(count):
        steps.append(("select_preset", (at, surface.FALLBACK_PRESET)))
    steps.append(("generate_all", ()))
    return bridge_payload(steps=steps)


class JsRuntime(JsEngine):
    """A QJSEngine holding ``audio_suite.js`` and a ``window`` global."""

    module_path = MODULE_PATH
    setter = "acervatorSetAudioSuite"

    def answer(self, call: str) -> Any:
        """One value the module's own namespace answers with."""
        return self.json("acervatorAudioSuite." + call)


@pytest.fixture()
def js(qapp) -> JsRuntime:
    """The module, loaded in a fresh engine."""
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


@pytest.fixture()
def loaded(js: JsRuntime) -> JsRuntime:
    """The module holding the real surface's whole payload."""
    js.push(bridge_payload())
    return js


# -- 1. the module answers the method the bridge serves -----------------


def test_the_module_asks_for_the_method_the_surface_answers(js: JsRuntime):
    """The module asked the bridge for a method no surface serves."""
    assert js.answer("method") == surface.METHOD


def test_the_bridge_serves_the_method_the_module_asks_for(js: JsRuntime):
    """The bridge lost the handler the module calls."""
    served = desktop_bridge.build_registry()
    assert js.answer("method") in served, sorted(served)


# -- 2. every field the module draws from reaches it --------------------


def test_every_field_the_module_declares_reaches_it_from_the_surface(
    loaded: JsRuntime,
):
    """A field the module draws from is in no payload the surface serves."""
    payload = bridge_payload()
    declared = loaded.answer("declaredFields()")
    assert declared, "the module declares no field at all"
    missing = sorted(name for name in declared if name not in payload)
    assert not missing, f"{len(missing)} declared fields never arrive: {missing}"
    assert loaded.answer("faults()") == []


def test_the_field_check_names_a_field_the_payload_never_carries(js: JsRuntime):
    """The field check passed because it looked at nothing."""
    payload = bridge_payload()
    dropped = js.answer("declaredFields()")[0]
    del payload[dropped]
    report = js.push(payload)
    named = [one["field"] for one in report["faults"]]
    assert named == [dropped], report["faults"]


def test_a_payload_that_is_not_an_object_is_refused(js: JsRuntime):
    """The module drew a screen from something that is not a payload."""
    report = js.push([])
    assert report["held"] is None
    assert [one["fault"] for one in report["faults"]] == ["not-an-object"]
    assert js.answer("isLoaded()") is False


# -- 3. the alpha byte becomes the share a browser reads ----------------


def test_the_trace_alpha_is_the_share_a_browser_reads(loaded: JsRuntime):
    """The module handed CSS Qt's alpha byte, which paints solid."""
    share = loaded.answer("traceAlphaShare()")
    assert share == css_alpha(surface.LAYER_TRACE_ALPHA), (
        f"the module publishes {share}, the shared converter answers "
        f"{css_alpha(surface.LAYER_TRACE_ALPHA)}"
    )
    assert share <= CSS_ALPHA_CEILING, share


def test_the_alpha_byte_itself_would_have_painted_the_traces_solid():
    """The control: the value the module must not hand a browser."""
    assert surface.LAYER_TRACE_ALPHA > CSS_ALPHA_CEILING, (
        "the surface no longer carries a Qt alpha byte, so the conversion "
        "the module performs proves nothing"
    )


def test_every_trace_stroke_carries_the_share_and_the_published_colour(
    loaded: JsRuntime,
):
    """A trace was stroked in a colour or an opacity the surface never named."""
    strokes = loaded.answer("traceStrokes()")
    assert len(strokes) == len(surface.LAYER_TRACE_COLOURS), strokes
    share = css_alpha(surface.LAYER_TRACE_ALPHA)
    for at, stroke in enumerate(strokes):
        published = surface.LAYER_TRACE_COLOURS[at]
        red = int(published[1:3], 16)
        green = int(published[3:5], 16)
        blue = int(published[5:7], 16)
        assert stroke == f"rgba({red},{green},{blue},{share})", (at, stroke, published)


def test_a_trace_stroke_reads_the_colour_red_first_not_alpha_first(
    loaded: JsRuntime,
):
    """Qt reads eight hex digits alpha first; a browser reads them red
    first. A trace stroked from the wrong end paints the wrong hue."""
    strokes = loaded.answer("traceStrokes()")
    first = surface.LAYER_TRACE_COLOURS[0]
    red_first = int(first[1:3], 16)
    alpha_first = int(first[3:5], 16)
    assert red_first != alpha_first, (
        "the first trace colour no longer tells the two readings apart, "
        "so this check cannot fail"
    )
    assert strokes[0].startswith(f"rgba({red_first},"), strokes[0]


# -- 4. what the waveform draws ----------------------------------------


def test_a_silent_waveform_draws_the_idle_caption_and_no_trace(js: JsRuntime):
    """The strip drew traces for layers that are not sounding."""
    js.push(bridge_payload())
    assert js.answer("layersDrawn()") == 0
    assert js.answer(f"drawnTraces({STRIP_WIDTH_PX}, 50)") == []


def test_a_sounding_waveform_draws_one_trace_for_each_layer(js: JsRuntime):
    """The positive control for the silent case: a trace does appear."""
    for count in (1, 2, 4):
        js.push(payload_with_layers(count, surface.DEFAULT_KEY))
        assert js.answer("layersDrawn()") == count, count
        drawn = js.answer(f"drawnTraces({STRIP_WIDTH_PX}, 50)")
        assert len(drawn) == count, count
        assert all(one for one in drawn), count


def test_more_layers_than_traces_draws_no_more_than_the_layer_total(
    js: JsRuntime,
):
    """A payload naming more layers than exist drew a trace with no colour."""
    payload = bridge_payload()
    payload["run"]["state"]["waveform_layers"] = surface.LAYER_TOTAL + 5
    js.push(payload)
    assert js.answer("layersDrawn()") == surface.LAYER_TOTAL


def test_every_trace_point_stays_inside_the_band_the_surface_names(
    loaded: JsRuntime,
):
    """A trace left the height the surface gives it and drew outside the strip."""
    height = surface.WAVEFORM_MIN_HEIGHT_PX
    middle = height * 0.5
    for layer in range(surface.LAYER_TOTAL):
        reach = loaded.answer(f"amplitudeOf({layer})")
        assert reach == (
            surface.TRACE_AMPLITUDE_BASE_PX + layer * surface.TRACE_AMPLITUDE_STEP_PX
        ), layer
        points = loaded.answer(f"traceOf({layer}, {STRIP_WIDTH_PX}, {height}, 0)")
        assert points, layer
        outside = [one for one in points if abs(one[1] - middle) > reach]
        assert outside == [], (layer, outside[:3], reach)


def test_the_band_check_names_a_point_outside_the_reach(loaded: JsRuntime):
    """The band check passed because every point was inside every band."""
    height = surface.WAVEFORM_MIN_HEIGHT_PX
    middle = height * 0.5
    reach = loaded.answer("amplitudeOf(0)")
    points = loaded.answer(f"traceOf(0, {STRIP_WIDTH_PX}, {height}, 0)")
    reached = max(abs(one[1] - middle) for one in points)
    assert reached > 0, "the first trace is flat, so no band can be tested"
    outside = [one for one in points if abs(one[1] - middle) > reached * 0.5]
    assert outside, (reach, reached)


def test_a_trace_steps_across_the_strip_by_the_published_step(
    loaded: JsRuntime,
):
    """A trace drew at a spacing no field of the payload names."""
    height = surface.WAVEFORM_MIN_HEIGHT_PX
    points = loaded.answer(f"traceOf(0, {STRIP_WIDTH_PX}, {height}, 0)")
    step = surface.LAYER_TRACE_STEP_PX
    assert [one[0] for one in points] == list(range(0, STRIP_WIDTH_PX, step))


def test_moving_the_phase_on_moves_every_trace(loaded: JsRuntime):
    """The waveform stood still while the tab said it was animating."""
    height = surface.WAVEFORM_MIN_HEIGHT_PX
    gain = surface.ANIMATION_PHASE_GAIN
    onwards = surface.ANIMATION_STEP_S * gain
    at_rest = loaded.answer(f"traceOf(0, {STRIP_WIDTH_PX}, {height}, 0)")
    moved = loaded.answer(f"traceOf(0, {STRIP_WIDTH_PX}, {height}, {onwards})")
    assert len(at_rest) == len(moved)
    assert at_rest != moved, "the phase reached no point of the trace"


def test_the_animation_delay_is_the_one_the_surface_publishes(loaded: JsRuntime):
    """The delay is READ, never timed. Chromium throttles a timer in a
    backgrounded view, so an elapsed-time check measures the host."""
    assert loaded.answer("animationDelays()") == dict(surface.TIMERS)


# -- 5. the wording the panels show ------------------------------------


def test_the_module_shows_the_control_wording_the_surface_publishes(
    loaded: JsRuntime,
):
    """A slider was labelled with wording that reaches no table."""
    assert loaded.answer("controlWording()") == dict(surface.CONTROL_LABELS)


def test_the_module_shows_the_drone_buttons_the_surface_publishes(
    loaded: JsRuntime,
):
    """A drone button carried wording that reaches no table."""
    assert loaded.answer("droneButtonLabels()") == list(surface.DRONE_BUTTON_LABELS)


def test_the_music_controls_are_absent_without_the_sound_library(js: JsRuntime):
    """The music player offered controls that reach no player."""
    js.push(bridge_payload(media=surface.MEDIA_LIBRARY_MISSING))
    assert js.answer("musicControlsShown()") is False
    js.push(bridge_payload(media=surface.MEDIA_READY))
    assert js.answer("musicControlsShown()") is True


def test_the_module_finds_the_library_missing_state_where_the_surface_lists_it():
    """The module reads the media state by position, so a reordered list
    would silently give the music player back its controls."""
    assert surface.MEDIA_STATES[2] == surface.MEDIA_LIBRARY_MISSING, list(
        surface.MEDIA_STATES
    )


def test_a_qt_selector_block_becomes_the_declarations_a_browser_reads(
    loaded: JsRuntime,
):
    """Qt wraps a sheet in its own selector. A browser reads none of it,
    so the block's contents are what the panel carries."""
    frame = loaded.answer('skinOf("layer_frame")')
    assert frame, surface.SKIN["layer_frame"]
    assert "QFrame" not in json.dumps(frame), frame
    assert set(frame) == {"border", "borderRadius"}, frame
    plain = loaded.answer('skinOf("music_play_button")')
    assert plain == {"fontWeight": "bold"}, plain


# -- 6. the module carries no value of its own -------------------------


# A value this short is punctuation, not a product value.
SHORTEST_VALUE = 2


def surface_text() -> tuple:
    """Every value the surface publishes, and every key it publishes under.

    A key is what the module is entitled to name; a value is what it must
    never spell out. Both are collected at every depth.
    """
    values: set = set()
    keys: set = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for name, one in value.items():
                keys.add(str(name))
                walk(one)
            return
        if isinstance(value, (list, tuple)):
            for one in value:
                walk(one)
            return
        if isinstance(value, bool) or value is None:
            return
        as_text = str(value)
        if len(as_text) >= SHORTEST_VALUE:
            values.add(as_text)

    walk(surface.build_view_model())
    return values, keys


PUBLISHED_VALUES, PUBLISHED_KEYS = surface_text()
SURFACE_VALUES = PUBLISHED_VALUES - PUBLISHED_KEYS


def test_the_module_writes_no_colour():
    """A colour spelled in the module is a second skin for one screen."""
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"{MODULE_NAME} holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_surface_publishes():
    """A value spelled in the module is a second source of truth."""
    written = sorted(set(MODULE_LITERALS["strings"]) & SURFACE_VALUES)
    assert not written, f"{MODULE_NAME} spells out surface values: {written}"


def test_every_number_the_module_writes_is_an_algorithm_constant():
    """A number outside the drawing arithmetic is a value the surface owns."""
    stray = sorted(set(MODULE_LITERALS["numbers"]) - ALGORITHM_NUMBERS)
    assert not stray, f"{MODULE_NAME} holds unexplained numbers: {stray}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    """A slash the scan cannot read could hide any value at all."""
    assert not MODULE_LITERALS["slashes"], MODULE_LITERALS["slashes"]


PLANTED_LINES = {
    "colour": 'var spelled = "' + surface.LAYER_TRACE_COLOURS[0] + '";',
    "wording": 'var spelled = "' + surface.CONTROL_LABELS["volume"] + '";',
    "caption": 'var spelled = "' + surface.WAVEFORM_IDLE_TEXT + '";',
    "measurement": "var spelled = " + str(surface.WAVEFORM_KEY_INSET_PX) + ";",
    "number": "var spelled = 4913;",
    "regex": "var spelled = /ab+c/;",
}


def caught_by_scan(source: str) -> set:
    """Which of the four checks report on `source`."""
    found = js_literals(source)
    caught = set()
    if HEX_COLOUR.findall(source):
        caught.add("colour")
    if set(found["strings"]) & SURFACE_VALUES:
        caught.add("value")
    if set(found["numbers"]) - ALGORITHM_NUMBERS:
        caught.add("number")
    if found["slashes"]:
        caught.add("slash")
    return caught


@pytest.mark.parametrize("kind", sorted(PLANTED_LINES))
def test_the_literal_scan_names_a_line_that_spells_a_value_out(kind: str):
    """The controls for the four scan checks."""
    assert caught_by_scan(PLANTED_LINES[kind]), kind


def test_the_value_set_still_holds_the_wording_a_screen_shows():
    """The value check passed because its set was emptied by the trim."""
    assert SURFACE_VALUES, "the surface publishes no value the module could spell"
    assert surface.WAVEFORM_IDLE_TEXT in SURFACE_VALUES
    assert surface.CONTROL_LABELS["volume"] in SURFACE_VALUES
    assert surface.LAYER_TRACE_COLOURS[0] in SURFACE_VALUES
    trimmed = {one for one in PUBLISHED_VALUES if len(one) < SHORTEST_VALUE}
    assert trimmed == set(), trimmed


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    """A colour inside a comment is not a value the module writes."""
    found = js_literals("// " + surface.LAYER_TRACE_COLOURS[0] + '\nvar k = "k";')
    assert found["strings"] == ["k"]
    assert not found["numbers"]


# -- 7. the renderer runs the module -----------------------------------


def test_the_renderer_runs_the_module_after_react():
    """A module the page never runs draws nothing, whatever it holds."""
    order = load_order()
    assert MODULE_NAME in order, order
    assert runs_after(order, MODULE_NAME, "module_loader.js"), order


# React does not replace a widget until the operational logs verify it.

# Class name -> how many the shipped tab holds with the sound library
# stood down. The private classes Qt builds inside a combo box are left out.
SHIPPED_CHILDREN = {
    "WaveformWidget": 1,
    "MusicPlayerPanel": 1,
    "DroneEnginePanel": 1,
    "DroneLayer": 4,
    "QSplitter": 1,
    "QComboBox": 6,
    "QSlider": 7,
    "QPushButton": 4,
    "QLabel": 19,
}


def live_children(tab: Any) -> dict:
    """How many of each counted class `tab` holds right now."""
    from PySide6.QtWidgets import QWidget

    seen = collections.Counter(
        one.metaObject().className() for one in tab.findChildren(QWidget)
    )
    return {name: seen.get(name, 0) for name in SHIPPED_CHILDREN}


@pytest.fixture()
def shipped_tab():
    """The real Qt tab, built with the sound library stood down."""
    from src.gui import audio_suite as shipped
    from tests.qt_pixel import ensure_app

    ensure_app()
    was = shipped._HAS_MEDIA
    shipped._HAS_MEDIA = False
    tab = shipped.AudioSuiteTab()
    tab._at.stop()
    try:
        yield tab
    finally:
        tab.close()
        tab.deleteLater()
        shipped._HAS_MEDIA = was


def test_the_shipped_qt_tab_still_holds_every_widget_it_built(shipped_tab: Any):
    """A Qt widget was deleted before its React replacement was verified."""
    assert live_children(shipped_tab) == SHIPPED_CHILDREN


def test_the_shipped_qt_tab_still_paints(shipped_tab: Any):
    """A tree that holds its widgets but paints nothing is not preserved.

    The colour is read off the composited image, never off a style sheet:
    a widget reports the colour it was TOLD to paint whether it painted
    or not.
    """
    from tests.qt_pixel import render_widget

    image = render_widget(shipped_tab, size=(STRIP_WIDTH_PX, 400))
    across = [image.width() // 8, image.width() // 2, image.width() - 2]
    down = [1, image.height() // 3]
    colours = {image.pixelColor(x, y).name() for x in across for y in down}
    assert len(colours) > 1, f"the tab painted one flat colour: {colours}"


def test_the_child_count_check_names_a_missing_widget(shipped_tab: Any):
    """The count check passed because it compared two empty tables."""
    assert SHIPPED_CHILDREN, "no class is counted, so nothing can be missed"
    blinded = live_children(shipped_tab)
    blinded["DroneLayer"] -= 1
    assert blinded != SHIPPED_CHILDREN, blinded
