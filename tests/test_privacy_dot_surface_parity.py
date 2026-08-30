"""The Qt privacy dot and the Qt-free surface, side by side.

A failure means the view model describes a different glyph, a different
tooltip, a different colour, a different button state, a different privacy
mask or a different branch than ``PrivacyDot`` produces on the same field
and the same clicks.
"""

from __future__ import annotations

import ast
import functools
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.main_tabs import privacy_dot_surface as surface
from tests.fixtures.host_fonts import (
    NARROW_TEXT,
    WIDE_TEXT,
    has_real_fonts,
    load_run_fonts,
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
WIDGET_SOURCE = REPO_ROOT / "src" / "gui" / "widgets" / "privacy_dot.py"
SURFACE_SOURCE = REPO_ROOT / "src" / "gui" / "main_tabs" / "privacy_dot_surface.py"
TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "history_tab.py"
TIMER_NAMESAKE = REPO_ROOT / "src" / "gui" / "main_tabs" / "history_tab.py"
BUS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"

PIXEL_SIZE = (40, 40)

CONNECT_TOTAL = 1
SHIPPED_CLASS_TOTAL = 1
SHIPPED_METHOD_TOTAL = 4
PAYLOAD_KEY_TOTAL = 17
CONSTANT_TOTAL = 24
TRACE_KEY_TOTAL = 3
DOT_KEY_TOTAL = 8

# The test owns this map so neither side is named from the other.
MASKED_BY_GLYPH = {"●": False, "○": True}


def app():
    """The one application object every render is taken against.

    The run's font choice is applied here rather than by whichever guarded
    test happens to run first, so the font state does not depend on order.
    """
    from tests.qt_pixel import ensure_app

    ensure_app()
    load_run_fonts()
    return ensure_app()


def render_offscreen(widget, size):
    from tests.qt_pixel import render_widget

    return render_widget(widget, size)


def digest(value) -> str:
    """SHA-256 over every value in `value`, at every depth."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True, default=repr).encode(
            "utf-8"
        )
    ).hexdigest()


def headline(message: str) -> str:
    """The first line of a refusal message.

    Qt names every signature it accepts under its first line, and a check
    reading the whole message compares a list of types rather than the
    refusal, so it can never report a wrong one.
    """
    return message.splitlines()[0] if message else message


def differences(old, new, prefix: str = "") -> list:
    """Every path at which two traces carry a different value."""
    found: list = []
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(set(old) | set(new), key=repr):
            found.extend(differences(old.get(key), new.get(key), f"{prefix}{key}."))
    elif isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        for index, (left, right) in enumerate(zip(old, new)):
            found.extend(differences(left, right, f"{prefix}{index}."))
    elif old != new:
        found.append(prefix.rstrip("."))
    return found


# ---------------------------------------------------------------------
# The privacy register is process-wide, and the dot WRITES to it. Every
# test is given its own and the process one is put back.
# ---------------------------------------------------------------------


@pytest.fixture(autouse=True)
def own_privacy_registry(tmp_path, monkeypatch):
    """Give this test its own register and restore the process one after.

    ``get_privacy_mask_registry`` returns one object for the whole process,
    both sides reach it through that one function, and a click writes to
    it, so a mask a test leaves set would decide what a later test paints.
    A NEW object is handed out rather than a cleared one: clearing touches
    only the field ids the register knows, so an unknown id would keep its
    value into the next test. Autosave is off and the path is a temporary
    one, so no test writes a settings file.
    """
    from src.core import privacy_mask_registry as registry_module

    fresh = registry_module.PrivacyMaskRegistry(
        settings_path=tmp_path / "settings.json", autosave=False
    )
    monkeypatch.setattr(registry_module, "_SINGLETON", fresh)
    yield fresh


def registry():
    """The register both sides read, through the accessor both sides call."""
    from src.core.privacy_mask_registry import get_privacy_mask_registry

    return get_privacy_mask_registry()


def registry_rows() -> list:
    """Every field the register holds, as text, in one settled order."""
    return sorted(
        [repr(key), bool(value)] for key, value in registry().to_dict().items()
    )


# ---------------------------------------------------------------------
# The inputs. One scenario drives both sides.
# ---------------------------------------------------------------------

LONG_TEXT = "L" * 200
MARKUP_TEXT = '<b onclick="x">bold &amp; "quoted"</b>'
UNICODE_TEXT = "₿ éèê BTC 交易 \U0001f680"
NEWLINE_TEXT = "kpi\nspendable"
APOSTROPHE_TEXT = "Ekthelius' venues"
WRONG_CAPITALS_TEXT = "KPI.Spendable"
HAPPY_FIELD_ID = "kpi.spendable"


class Unnameable:
    """A field id whose name cannot be read."""

    def __str__(self):
        raise ValueError("this field id cannot be named")


class UnnameableType:
    """A field id whose name cannot be built."""

    def __str__(self):
        raise TypeError("this field id has no name to build")


def scenario(
    name,
    field_id=HAPPY_FIELD_ID,
    masked_first=False,
    steps=(),
    callback="none",
    dots=1,
):
    return {
        "name": name,
        "field_id": field_id,
        "masked_first": masked_first,
        "steps": tuple(steps),
        "callback": callback,
        "dots": dots,
    }


SCENARIOS = [
    scenario("happy"),
    scenario("built_only_starts_masked", masked_first=True),
    scenario("empty_field_id", field_id=""),
    scenario("zero_where_text_belongs", field_id=0),
    scenario("negative_where_text_belongs", field_id=-1),
    scenario("a_thousand_million_where_text_belongs", field_id=1_000_000_000),
    scenario("one_billionth_where_text_belongs", field_id=1e-9),
    scenario("a_whole_number_where_text_belongs", field_id=12),
    scenario("a_decimal_where_text_belongs", field_id=12.0),
    scenario("infinity_where_text_belongs", field_id=math.inf),
    scenario("negative_infinity_where_text_belongs", field_id=-math.inf),
    scenario("not_a_number_where_text_belongs", field_id=math.nan),
    scenario("a_flag_where_text_belongs", field_id=True),
    scenario("nothing_where_text_belongs", field_id=None),
    scenario("unicode_field_id", field_id=UNICODE_TEXT),
    scenario("two_hundred_characters", field_id=LONG_TEXT),
    scenario("markup_in_the_field_id", field_id=MARKUP_TEXT),
    scenario("apostrophe_in_the_field_id", field_id=APOSTROPHE_TEXT),
    scenario("wrong_capitals_in_the_field_id", field_id=WRONG_CAPITALS_TEXT),
    scenario("newline_in_the_field_id", field_id=NEWLINE_TEXT),
    scenario("a_field_id_the_register_cannot_hold", field_id=["kpi.spendable"]),
    scenario(
        "a_field_id_the_register_cannot_hold_clicked",
        field_id={"kpi": "spendable"},
        steps=("click",),
    ),
    scenario("a_field_id_that_cannot_be_named", field_id=Unnameable()),
    scenario("a_field_id_whose_name_is_not_text", field_id=UnnameableType()),
    scenario("clicked_once", steps=("click",)),
    scenario("clicked_twice", steps=("click", "click")),
    scenario("clicked_three_times", steps=("click", "click", "click")),
    scenario("clicked_then_refreshed", steps=("click", "refresh")),
    scenario("refreshed_only", steps=("refresh",)),
    scenario("masked_outside_then_refreshed", steps=("mask", "refresh")),
    scenario(
        "unmasked_outside_then_refreshed",
        masked_first=True,
        steps=("unmask", "refresh"),
    ),
    scenario("masked_outside_then_clicked", steps=("mask", "click")),
    scenario("clicked_from_masked", masked_first=True, steps=("click",)),
    scenario("attached_twice_then_clicked", dots=2, steps=("click",)),
    scenario("attached_twice_then_clicked_twice", dots=2, steps=("click", "click")),
    scenario("attached_twice_then_refreshed", dots=2, steps=("mask", "refresh")),
    scenario("a_callback_that_runs", steps=("click",), callback="recorder"),
    scenario("a_callback_that_raises", steps=("click",), callback="raiser"),
    scenario(
        "a_callback_that_is_not_callable", steps=("click",), callback="not_callable"
    ),
    scenario(
        "a_callback_that_runs_on_every_click",
        steps=("click", "click"),
        callback="recorder",
    ),
    scenario(
        "a_callback_on_a_field_the_register_cannot_hold",
        field_id=["kpi.locked"],
        steps=("click",),
        callback="recorder",
    ),
]

SCENARIO_NAMES = [spec["name"] for spec in SCENARIOS]
BY_NAME = {spec["name"]: spec for spec in SCENARIOS}

REFUSING_SCENARIOS = (
    "a_field_id_that_cannot_be_named",
    "a_field_id_whose_name_is_not_text",
)


def callback_for(spec, recorder):
    """The on-toggle callback one scenario asks for."""
    kind = spec["callback"]
    if kind == "none":
        return None
    if kind == "not_callable":
        return "not a function"
    if kind == "recorder":
        return lambda: recorder.append("ran")

    def raiser():
        recorder.append("ran")
        raise RuntimeError("the owner's callback failed")

    return raiser


def set_start_mask(spec) -> None:
    """Put the register into the state the scenario starts from."""
    live = registry()
    live.set_all(False)
    if spec["masked_first"]:
        live.set_masked(spec["field_id"], True)


def run_steps(spec, dots, click) -> None:
    """Drive one scenario's step sequence over every dot it built."""
    for step in spec["steps"]:
        if step == "mask":
            registry().set_masked(spec["field_id"], True)
        elif step == "unmask":
            registry().set_masked(spec["field_id"], False)
        elif step == "click":
            for dot in dots:
                click(dot)
        else:
            for dot in dots:
                dot.refresh()


# ---------------------------------------------------------------------
# Driving the two sides
# ---------------------------------------------------------------------


def drive_old(spec):
    """The shipped Qt dot, built and driven by one scenario."""
    from src.gui.widgets.privacy_dot import PrivacyDot

    app()
    set_start_mask(spec)
    recorder: list = []
    dots = [
        PrivacyDot(spec["field_id"], on_toggle=callback_for(spec, recorder))
        for _ in range(spec["dots"])
    ]
    run_steps(spec, dots, lambda dot: dot.click())
    return dots, recorder


def drive_new(spec):
    """The Qt-free model, built and driven by the same scenario."""
    set_start_mask(spec)
    recorder: list = []
    models = [
        surface.PrivacyDotModel(
            spec["field_id"], on_toggle=callback_for(spec, recorder)
        )
        for _ in range(spec["dots"])
    ]
    run_steps(spec, models, lambda model: model.clicked())
    return models, recorder


# ---------------------------------------------------------------------
# Reading the two sides
# ---------------------------------------------------------------------


def dot_from_qt(dot) -> dict:
    """One dot, read off the widget the shipped class built."""
    painted = dot.text()
    return {
        "field_id": repr(dot.field_id()),
        "text": painted,
        "tooltip": dot.toolTip(),
        "style_sheet": dot.styleSheet(),
        "flat": dot.isFlat(),
        "focus_policy": dot.focusPolicy().name,
        "cursor_shape": dot.cursor().shape().name,
        "masked": MASKED_BY_GLYPH[painted],
    }


def dot_from_payload(payload) -> dict:
    """The same reading, taken off the view model alone."""
    return {
        "field_id": repr(payload["field_id"]),
        "text": payload["text"],
        "tooltip": payload["tooltip"],
        "style_sheet": payload["style_sheet"],
        "flat": payload["flat"],
        "focus_policy": payload["focus_policy"],
        "cursor_shape": payload["cursor_shape"],
        "masked": payload["masked"],
    }


def qt_trace(driven) -> dict:
    """Everything the shipped dot shows, plus what it wrote and ran."""
    dots, recorder = driven
    return {
        "dots": [dot_from_qt(dot) for dot in dots],
        "callback": list(recorder),
        "register": registry_rows(),
    }


def surface_trace(driven) -> dict:
    """The same reading, taken off the view models alone."""
    models, recorder = driven
    return {
        "dots": [dot_from_payload(surface.build_view_model(m)) for m in models],
        "callback": list(recorder),
        "register": registry_rows(),
    }


def outcome(work) -> dict:
    """What one side did: the value it answered, or the error it refused with."""
    try:
        return {"outcome": "answered", "value": work()}
    except Exception as exc:
        return {
            "outcome": "refused",
            "error": type(exc).__name__,
            "message": str(exc),
            "headline": headline(str(exc)),
        }


def old_outcome(spec) -> dict:
    return outcome(lambda: qt_trace(drive_old(spec)))


def new_outcome(spec) -> dict:
    return outcome(lambda: surface_trace(drive_new(spec)))


# ---------------------------------------------------------------------
# The two sides, value for value and by hash
# ---------------------------------------------------------------------


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_the_two_sides_describe_the_same_dot(name):
    """A glyph, tooltip, colour, button state or privacy mask differs."""
    spec = BY_NAME[name]
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert new["outcome"] == old["outcome"], (name, old, new)
    if old["outcome"] == "refused":
        assert new["error"] == old["error"], (name, old, new)
        assert new["headline"] == old["headline"], (name, old, new)
        return
    moved = differences(old["value"], new["value"])
    assert moved == [], (name, moved, old["value"], new["value"])
    assert new["value"] == old["value"], name
    assert digest(new["value"]) == digest(old["value"]), name


def test_both_answers_and_refusals_are_in_the_measured_set():
    """Every input was accepted, so no refusal was ever compared."""
    answered = []
    refused = []
    for spec in SCENARIOS:
        old = old_outcome(spec)
        (answered if old["outcome"] == "answered" else refused).append(spec["name"])
    assert answered, "no input was answered"
    assert refused, "no input was refused"
    assert set(refused) == set(REFUSING_SCENARIOS), sorted(refused)
    assert len(answered) + len(refused) == len(SCENARIOS)


@pytest.mark.parametrize("name", REFUSING_SCENARIOS)
def test_a_refused_field_id_names_the_same_error_on_both_sides(name):
    """One side refused a field the other accepted, or named another error."""
    spec = BY_NAME[name]
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert old["outcome"] == "refused", (name, old)
    assert new["outcome"] == "refused", (name, new)
    assert (new["error"], new["headline"]) == (old["error"], old["headline"])
    assert old["error"] in ("TypeError", "ValueError")


def test_the_two_refusals_name_two_different_errors():
    """Both refusals name one error, so the error check compares nothing."""
    named = {}
    for name in REFUSING_SCENARIOS:
        refused = old_outcome(BY_NAME[name])
        named[name] = (refused["error"], refused["headline"])
    assert len(set(named.values())) == len(REFUSING_SCENARIOS), named
    assert named["a_field_id_that_cannot_be_named"][0] == "ValueError"
    assert named["a_field_id_whose_name_is_not_text"][0] == "TypeError"


def test_the_headline_reader_trims_a_message_that_lists_every_type():
    """The headline reader returns the whole message, so it cannot report.

    Qt names every signature it accepts under the first line of its
    refusal, and a check reading the whole message would compare that list
    rather than the refusal.
    """
    app()
    from PySide6.QtWidgets import QPushButton

    with pytest.raises(TypeError) as reported:
        QPushButton(object())
    whole = str(reported.value)
    assert len(whole.splitlines()) > 1, whole
    assert len(headline(whole).splitlines()) == 1
    assert headline(whole) in whole
    assert headline("one line only") == "one line only"


def test_the_hash_tells_two_different_answers_apart():
    """The hash returns one value whatever it is given, so it proves nothing."""
    revealed = old_outcome(BY_NAME["happy"])["value"]
    masked = old_outcome(BY_NAME["built_only_starts_masked"])["value"]
    assert revealed != masked
    assert digest(revealed) != digest(masked)
    assert digest(revealed) == digest(old_outcome(BY_NAME["happy"])["value"])
    assert len(digest(revealed)) == 64
    settled = old_outcome(BY_NAME["clicked_once"])["value"]
    assert digest(settled) == digest(masked), (
        "two inputs that settle on one state are no control; the pair above "
        "must settle on two"
    )


def test_the_hash_tells_a_whole_number_from_a_decimal():
    """A field id of 12 and one of 12.0 hash the same, so a change hides.

    The two compare equal as numbers. The trace carries each as its own
    text, so the hash tells them apart.
    """
    assert 12 == 12.0
    whole = old_outcome(BY_NAME["a_whole_number_where_text_belongs"])["value"]
    decimal = old_outcome(BY_NAME["a_decimal_where_text_belongs"])["value"]
    assert whole["dots"][0]["field_id"] == "12"
    assert decimal["dots"][0]["field_id"] == "12.0"
    assert digest(whole) != digest(decimal)


def test_a_not_a_number_field_id_compares_as_text_on_both_sides():
    """Two not-a-numbers were compared as numbers, which is never equal.

    The trace carries the field id as its own text, so the comparison
    reports a real difference rather than the one every not-a-number has
    with itself.
    """
    assert math.nan != math.nan
    spec = BY_NAME["not_a_number_where_text_belongs"]
    old = old_outcome(spec)["value"]
    new = new_outcome(spec)["value"]
    assert old["dots"][0]["field_id"] == "nan"
    assert differences(old, new) == []
    assert digest(old) == digest(new)


@pytest.mark.parametrize(
    "name",
    [
        "happy",
        "built_only_starts_masked",
        "clicked_once",
        "attached_twice_then_clicked",
    ],
)
def test_the_sample_hashes_are_reported(name):
    """The comparison passed on a trace that carries nothing."""
    value = old_outcome(BY_NAME[name])["value"]
    assert isinstance(value, dict)
    assert len(value) == TRACE_KEY_TOTAL, sorted(value)
    assert len(value["dots"]) == BY_NAME[name]["dots"]
    assert len(value["dots"][0]) == DOT_KEY_TOTAL, sorted(value["dots"][0])
    assert value["register"], "the register snapshot is empty"
    assert digest(value) == digest(new_outcome(BY_NAME[name])["value"])


def test_the_comparison_reports_a_value_that_moved(monkeypatch):
    """The comparison passes a dot painting the wrong glyph.

    The shipped class is made to paint another character, which the glyph
    reader refuses. A value moved inside a trace must be named by path.
    """
    app()
    from src.gui.widgets.privacy_dot import PrivacyDot

    before = old_outcome(BY_NAME["happy"])["value"]
    original = PrivacyDot.refresh

    def moved(self):
        original(self)
        self.setText("X")

    monkeypatch.setattr(PrivacyDot, "refresh", moved)
    after = old_outcome(BY_NAME["happy"])
    assert after["outcome"] == "refused", after
    assert after["error"] == "KeyError"
    monkeypatch.undo()
    shifted = json.loads(json.dumps(before))
    shifted["dots"][0]["tooltip"] = "moved"
    assert differences(before, shifted) == ["dots.0.tooltip"]
    assert differences(before, before) == []


def test_a_click_masks_the_field_and_re_renders_on_both_sides():
    """The shipped dot is wired to nothing, so a click changes no mask."""
    dots, _ = drive_old(BY_NAME["happy"])
    before = dot_from_qt(dots[0])
    dots[0].click()
    after = dot_from_qt(dots[0])
    assert before["text"] == surface.REVEALED_GLYPH
    assert after["text"] == surface.MASKED_GLYPH
    assert registry().is_masked(HAPPY_FIELD_ID) is True
    model = surface.PrivacyDotModel(HAPPY_FIELD_ID)
    assert model.text == surface.MASKED_GLYPH
    assert dot_from_payload(surface.build_view_model(model)) == after


def test_a_second_click_reveals_the_field_again_on_both_sides():
    """The dot only masks, so a second click leaves the value hidden."""
    old = old_outcome(BY_NAME["clicked_twice"])["value"]
    new = new_outcome(BY_NAME["clicked_twice"])["value"]
    assert old["dots"][0]["text"] == surface.REVEALED_GLYPH
    assert old["dots"][0]["masked"] is False
    assert differences(old, new) == []
    once = old_outcome(BY_NAME["clicked_once"])["value"]
    assert once["dots"][0]["text"] == surface.MASKED_GLYPH


def test_a_dot_keeps_a_stale_glyph_when_a_second_dot_flips_its_field():
    """A dot repaints when another dot on its field flips the mask.

    Only the clicked dot repaints, so a second dot on one field leaves the
    first showing the mask state that has just been undone. Measured on
    the shipped widget; the surface carries the same behaviour.
    """
    old = old_outcome(BY_NAME["attached_twice_then_clicked"])["value"]
    new = new_outcome(BY_NAME["attached_twice_then_clicked"])["value"]
    assert len(old["dots"]) == 2
    assert old["dots"][0]["text"] == surface.MASKED_GLYPH
    assert old["dots"][1]["text"] == surface.REVEALED_GLYPH
    assert old["register"] == new["register"]
    assert differences(old, new) == []


def test_a_refresh_puts_every_dot_on_one_field_back_in_step():
    """A repaint left a dot showing a mask its field no longer carries."""
    old = old_outcome(BY_NAME["attached_twice_then_refreshed"])["value"]
    new = new_outcome(BY_NAME["attached_twice_then_refreshed"])["value"]
    assert [dot["text"] for dot in old["dots"]] == [surface.MASKED_GLYPH] * 2
    assert differences(old, new) == []


# ---------------------------------------------------------------------
# The enumeration: connect sites, classes, methods, timers, bus topics
# ---------------------------------------------------------------------


def dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def connect_sites(path) -> list:
    """Every ``.connect(`` site in `path`, as signal and target."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "connect"
        ):
            target = node.args[0]
            found.append(
                (
                    dotted(node.func.value),
                    "lambda" if isinstance(target, ast.Lambda) else dotted(target),
                )
            )
    return sorted(found)


def test_the_dot_connects_one_signal_and_the_surface_names_one_action():
    """The wired click is missing on one side, or the counter reports nothing.

    The shipped file holds the one wired signal, so it is its own positive
    control. The surface holds none, which is the negative the same counter
    reports.
    """
    sites = connect_sites(WIDGET_SOURCE)
    assert sites == [("self.clicked", "self._on_click")], sites
    assert len(sites) == CONNECT_TOTAL
    assert len(surface.ACTIONS) == CONNECT_TOTAL
    assert surface.ACTIONS == {"clicked": "clicked"}
    assert WIDGET_SOURCE.read_text(encoding="utf-8").count(".connect(") == len(sites)
    assert connect_sites(SURFACE_SOURCE) == []
    assert callable(surface.PrivacyDotModel.clicked)


SHIPPED_METHODS = {
    "__init__": "PrivacyDotModel.__init__",
    "field_id": "PrivacyDotModel.field_id",
    "_on_click": "PrivacyDotModel.clicked",
    "refresh": "PrivacyDotModel.refresh",
}

SURFACE_CLASSES = {"PrivacyDotModel": "PrivacyDot"}


def declared_methods(holder) -> list:
    """Every method `holder` declares, read off the class object.

    A Qt signal is declared on the class and is callable, so a reader that
    accepted every callable would count one as a method.
    """
    return sorted(
        name
        for name, value in vars(holder).items()
        if callable(value)
        and type(value).__name__ != "Signal"
        and (not name.startswith("__") or name == "__init__")
    )


def test_every_shipped_class_and_method_has_a_counterpart():
    """The shipped dot gained or lost a class or a method."""
    from src.gui.widgets import privacy_dot as shipped

    classes = [
        name
        for name, value in vars(shipped).items()
        if isinstance(value, type) and value.__module__ == shipped.__name__
    ]
    assert classes == ["PrivacyDot"], classes
    assert len(classes) == SHIPPED_CLASS_TOTAL
    found = declared_methods(shipped.PrivacyDot)
    assert found == sorted(SHIPPED_METHODS), found
    assert len(found) == SHIPPED_METHOD_TOTAL
    for counterpart in SHIPPED_METHODS.values():
        holder, _, attribute = counterpart.partition(".")
        assert callable(getattr(getattr(surface, holder), attribute)), counterpart


def test_every_surface_class_names_what_it_replaces():
    """The surface grew a class that stands in for nothing on the Qt side."""
    built = sorted(
        name
        for name, value in vars(surface).items()
        if isinstance(value, type) and value.__module__ == surface.__name__
    )
    assert built == sorted(SURFACE_CLASSES), built
    assert SURFACE_CLASSES["PrivacyDotModel"] == "PrivacyDot"
    assert declared_methods(surface.PrivacyDotModel) == [
        "__init__",
        "clicked",
        "field_id",
        "refresh",
    ]


def test_the_method_reader_counts_no_signal_as_a_method():
    """A signal is callable and declared, so the counter reports one too many.

    The shipped dot declares no signal of its own, so the reader is pointed
    at a class that does. A counter returning nothing on both would be no
    measurement.
    """
    app()
    from src.gui.launcher import ModeCard

    declared = vars(ModeCard)
    signals = [
        name for name, value in declared.items() if type(value).__name__ == "Signal"
    ]
    assert signals, "the signal counter reports nothing"
    assert all(callable(declared[name]) for name in signals), signals
    assert not set(signals) & set(declared_methods(ModeCard)), signals
    assert "__init__" in declared_methods(ModeCard)
    assert "InventedMethod" not in SHIPPED_METHODS
    with pytest.raises(AttributeError):
        getattr(surface, "InventedModel")


def timer_sites(path) -> list:
    """Every ``QTimer(`` construction in `path`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and dotted(node.func).endswith("QTimer")
    ]


def bus_sites(path) -> list:
    """Every ``subscribe(`` site in `path`, as the topic it names."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "subscribe"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            found.append(node.args[0].value)
    return sorted(found)


def test_the_dot_holds_no_timer_and_the_counter_can_report():
    """The dot runs a timer the surface declares no delay for.

    The counter is pointed at a file that builds one. It counts the
    construction: a count of the NAME would also count the import line and
    report a file that builds none.
    """
    assert timer_sites(WIDGET_SOURCE) == []
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    built = timer_sites(TIMER_NEIGHBOUR)
    assert len(built) == 1, "the timer counter reports nothing"
    named = TIMER_NEIGHBOUR.read_text(encoding="utf-8").count("QTimer")
    assert named > len(built), (named, len(built))
    assert timer_sites(TIMER_NAMESAKE) == [], "the control file is named by path"
    assert TIMER_NEIGHBOUR.name == TIMER_NAMESAKE.name


def test_the_dot_subscribes_to_no_bus_topic_and_the_counter_can_report():
    """The dot listens on a topic the surface names none of."""
    assert bus_sites(WIDGET_SOURCE) == []
    assert surface.BUS_TOPICS == ()
    neighbour = bus_sites(BUS_NEIGHBOUR)
    assert len(neighbour) >= 2, "the bus counter reports nothing"
    assert "wire.created" in neighbour


# ---------------------------------------------------------------------
# The completeness check
# ---------------------------------------------------------------------


def named_payloads() -> dict:
    """The view model the completeness check reads."""
    registry().set_all(False)
    return {"built": surface.build_view_model()}


PAYLOAD_KEYS = {
    "ACTIONS": "built:actions",
    "BUS_TOPICS": "built:bus_topics",
    "CALL_NAMES": "built:call_names",
    "CURSOR_SHAPE": "built:cursor_shape",
    "DEFAULT_FIELD_ID": "built:field_id",
    "DOT_STYLE": "built:style_sheet",
    "FLAT": "built:flat",
    "FOCUS_POLICY": "built:focus_policy",
    "MASKED_GLYPH": "built:glyphs.masked",
    "MASKED_STATE": "built:states.masked",
    "METHOD": "built:method",
    "REVEALED_GLYPH": "built:glyphs.revealed",
    "REVEALED_STATE": "built:states.revealed",
    "TIMERS": "built:timers",
    "TIMER_DELAYS_MS": "built:timer_delays_ms",
}

# Values a payload carries inside a longer string rather than alone.
TEXT_INSIDE = {"TOOLTIP_SEPARATOR": "built:tooltip"}

# The eight branch markers, each carried inside call_names.
CALL_CONSTANTS = (
    "BUILT",
    "CLICKED",
    "TOGGLE_FAILED",
    "REFRESHED",
    "REGISTRY_UNREADABLE",
    "CALLBACK_RAN",
    "CALLBACK_FAILED",
    "CALLBACK_SKIPPED",
)

# Values no snapshot key carries, with the check that covers each.
NOT_IN_THE_SNAPSHOT: dict = {}

# Snapshot keys built from other values rather than carrying one.
DERIVED_KEYS = {
    "text": "test_the_two_sides_describe_the_same_dot",
    "masked": "test_the_two_sides_describe_the_same_dot",
    "calls": "test_every_branch_marker_fires_and_ties_to_what_the_operator_sees",
}


def at_path(payloads, path):
    """The value one ``name:dotted.path`` names."""
    name, _, dotted_path = path.partition(":")
    found = payloads[name]
    for step in dotted_path.split("."):
        found = found[int(step)] if step.isdigit() else found[step]
    return found


def surface_constants() -> dict:
    """Every value the surface exports that is not a function or a class."""
    import types

    return {
        name: value
        for name, value in vars(surface).items()
        if not name.startswith("_")
        and not callable(value)
        and not isinstance(value, types.ModuleType)
        and name != "annotations"
    }


def as_json_shape(value):
    """`value` with every tuple turned into the list a payload carries."""
    if isinstance(value, (list, tuple)):
        return [as_json_shape(inner) for inner in value]
    if isinstance(value, dict):
        return {key: as_json_shape(inner) for key, inner in value.items()}
    return value


def unaccounted_constants(payloads, constants) -> list:
    """The exported values that reach no snapshot and no named check."""
    unaccounted = []
    for name, value in constants.items():
        if name in PAYLOAD_KEYS:
            assert at_path(payloads, PAYLOAD_KEYS[name]) == as_json_shape(value), name
        elif name in TEXT_INSIDE:
            assert value in at_path(payloads, TEXT_INSIDE[name]), name
        elif name in CALL_CONSTANTS:
            assert value in payloads["built"]["call_names"], name
        elif name in NOT_IN_THE_SNAPSHOT:
            covered_by = NOT_IN_THE_SNAPSHOT[name]
            assert covered_by in globals(), (name, covered_by)
            assert callable(globals()[covered_by]), (name, covered_by)
        else:
            unaccounted.append(name)
    return unaccounted


def unbacked_keys(built) -> set:
    """The snapshot keys no exported value and no named check backs."""
    answered = {path.partition(":")[2].split(".")[0] for path in PAYLOAD_KEYS.values()}
    answered |= {path.partition(":")[2].split(".")[0] for path in TEXT_INSIDE.values()}
    answered.add("call_names")
    return set(built) ^ (answered | set(DERIVED_KEYS))


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface exports is in no snapshot the tests read.

    A comparison that reads some of the values passes whether the rest
    match or not.
    """
    constants = surface_constants()
    assert len(constants) == CONSTANT_TOTAL, sorted(constants)
    found = unaccounted_constants(named_payloads(), constants)
    assert found == [], found
    assert len(PAYLOAD_KEYS) == 15
    assert len(TEXT_INSIDE) == 1
    assert len(CALL_CONSTANTS) == 8
    assert len(PAYLOAD_KEYS) + len(TEXT_INSIDE) + len(CALL_CONSTANTS) == CONSTANT_TOTAL


def test_every_snapshot_key_carries_a_value_the_surface_holds():
    """The snapshot grew a key no value on the surface backs."""
    built = surface.build_view_model()
    assert unbacked_keys(built) == set(), sorted(unbacked_keys(built))
    assert len(built) == PAYLOAD_KEY_TOTAL
    for key, covered_by in DERIVED_KEYS.items():
        assert key in built
        assert callable(globals()[covered_by]), (key, covered_by)


def test_both_completeness_checks_report_what_they_are_given():
    """Both completeness checks passed because they look at nothing.

    A value the surface exports that reaches no snapshot must land in the
    unaccounted list, and a snapshot key no value backs must land in the
    unbacked set. Neither is shown by removing anything from the product:
    an invented value and an invented key are handed to the same two
    readers the checks above call.
    """
    payloads = named_payloads()
    constants = dict(surface_constants())
    constants["INVENTED_CONSTANT"] = "never in any snapshot"
    assert unaccounted_constants(payloads, constants) == ["INVENTED_CONSTANT"]
    assert unaccounted_constants(payloads, surface_constants()) == []
    grown = dict(payloads["built"])
    grown["invented_key"] = 1
    assert unbacked_keys(grown) == {"invented_key"}
    assert unbacked_keys(payloads["built"]) == set()
    shrunk = {key: value for key, value in payloads["built"].items() if key != "states"}
    assert unbacked_keys(shrunk) == {"states"}
    assert "build_view_model" not in surface_constants()
    assert "PrivacyDotModel" not in surface_constants()
    assert "view_model" not in surface_constants()
    with pytest.raises(KeyError):
        at_path(payloads, "built:glyphs.invented")


def test_every_branch_marker_fires_and_ties_to_what_the_operator_sees():
    """A branch the surface declares is never taken, or takes silently."""
    seen = set()
    for spec in SCENARIOS:
        if spec["name"] in REFUSING_SCENARIOS:
            continue
        for model in drive_new(spec)[0]:
            seen.update(model.calls)
    assert seen == set(surface.CALL_NAMES), sorted(set(surface.CALL_NAMES) - seen)
    unreadable = drive_new(BY_NAME["a_field_id_the_register_cannot_hold_clicked"])[0][0]
    assert surface.TOGGLE_FAILED in unreadable.calls
    assert surface.REGISTRY_UNREADABLE in unreadable.calls
    assert unreadable.text == surface.REVEALED_GLYPH
    failed = drive_new(BY_NAME["a_callback_that_raises"])[0][0]
    assert failed.calls.count(surface.CALLBACK_FAILED) == 1
    assert surface.CALLBACK_RAN not in failed.calls
    skipped = drive_new(BY_NAME["a_callback_that_is_not_callable"])[0][0]
    assert skipped.calls.count(surface.CALLBACK_SKIPPED) == 1
    ran = drive_new(BY_NAME["a_callback_that_runs_on_every_click"])[0][0]
    assert ran.calls.count(surface.CALLBACK_RAN) == 2


def test_a_callback_that_raises_is_swallowed_on_both_sides():
    """A failing callback stopped the dot from repainting."""
    old = old_outcome(BY_NAME["a_callback_that_raises"])
    new = new_outcome(BY_NAME["a_callback_that_raises"])
    assert old["outcome"] == "answered", old
    assert old["value"]["callback"] == ["ran"]
    assert old["value"]["dots"][0]["text"] == surface.MASKED_GLYPH
    assert differences(old["value"], new["value"]) == []


# ---------------------------------------------------------------------
# The surface carries its own values
# ---------------------------------------------------------------------


def test_the_surface_does_not_follow_a_value_moved_in_the_shipped_dot(monkeypatch):
    """The surface read its values off the dot it replaces.

    A surface that read the shipped dot would follow it, and the whole
    comparison above would be one side read twice. The skin and the tooltip
    the shipped class paints are moved and the surface must not move.
    """
    app()
    from src.gui.widgets.privacy_dot import PrivacyDot

    before = dot_from_qt(drive_old(BY_NAME["happy"])[0][0])
    original = PrivacyDot.refresh

    def moved(self):
        original(self)
        self.setStyleSheet("PrivacyDot { color: #ff00ff; font-size: 99px; }")
        self.setToolTip("moved")

    monkeypatch.setattr(PrivacyDot, "refresh", moved)
    after = dot_from_qt(drive_old(BY_NAME["happy"])[0][0])
    assert after["style_sheet"] == "PrivacyDot { color: #ff00ff; font-size: 99px; }"
    assert sorted(differences(before, after)) == ["style_sheet", "tooltip"]
    mine = dot_from_payload(surface.build_view_model(drive_new(BY_NAME["happy"])[0][0]))
    assert mine["style_sheet"] == before["style_sheet"] == surface.DOT_STYLE
    assert mine["tooltip"] == before["tooltip"]
    monkeypatch.undo()
    assert dot_from_qt(drive_old(BY_NAME["happy"])[0][0]) == before


def test_the_surface_does_not_follow_a_dot_that_builds_nothing(monkeypatch):
    """The surface asked the shipped dot to build its glyph."""
    app()
    from src.gui.widgets import privacy_dot as shipped

    before = surface.build_view_model()
    monkeypatch.setattr(shipped.PrivacyDot, "__init__", _blank_init)
    stripped = shipped.PrivacyDot("kpi.locked")
    assert stripped.text() == ""
    assert surface.build_view_model() == before
    assert before["text"] == surface.REVEALED_GLYPH
    monkeypatch.undo()
    assert shipped.PrivacyDot("kpi.locked").text() == surface.REVEALED_GLYPH


def _blank_init(self, *args, **named):
    """A dot constructor that paints nothing at all."""
    from PySide6.QtWidgets import QPushButton

    QPushButton.__init__(self, named.get("parent"))


def test_the_default_field_id_is_one_the_privacy_register_knows():
    """The surface names a field the privacy register cannot mask."""
    from src.core.privacy_mask_registry import ALL_FIELD_IDS

    assert surface.DEFAULT_FIELD_ID in ALL_FIELD_IDS
    assert "kpi.invented" not in ALL_FIELD_IDS


# ---------------------------------------------------------------------
# The shared privacy register
# ---------------------------------------------------------------------


def test_a_click_writes_to_the_process_wide_privacy_register():
    """The shipped dot changes no shared state, so no test can disturb another."""
    live = registry()
    live.set_all(False)
    assert live.is_masked(HAPPY_FIELD_ID) is False
    dots, _ = drive_old(BY_NAME["happy"])
    dots[0].click()
    assert live.is_masked(HAPPY_FIELD_ID) is True
    assert registry() is live


def test_clearing_the_register_keeps_a_field_it_does_not_know():
    """Clearing the register clears every field, so a fresh one is not needed.

    ``set_all`` walks only the field ids the register declares. A dot on
    any other id would carry its mask into the next test, which is why the
    fixture hands out a NEW register rather than a cleared one.
    """
    from src.core.privacy_mask_registry import PrivacyMaskRegistry

    live = registry()
    live.set_masked("invented.field", True)
    live.set_all(False)
    assert live.is_masked("invented.field") is True
    assert live.is_masked(HAPPY_FIELD_ID) is False
    assert PrivacyMaskRegistry(autosave=False).is_masked("invented.field") is False


def test_no_test_writes_a_settings_file(own_privacy_registry, tmp_path):
    """A click wrote the operator's live settings file."""
    dots, _ = drive_old(BY_NAME["happy"])
    dots[0].click()
    drive_new(BY_NAME["clicked_once"])
    assert not (tmp_path / "settings.json").exists()
    assert list(tmp_path.iterdir()) == []
    assert own_privacy_registry.is_masked(HAPPY_FIELD_ID) is True


def test_each_test_is_given_its_own_register():
    """Two tests share one register, so the order they run in decides both."""
    from src.core import privacy_mask_registry as registry_module

    assert registry() is registry_module._SINGLETON
    assert registry().is_masked(HAPPY_FIELD_ID) is False
    registry().set_masked(HAPPY_FIELD_ID, True)
    assert registry().is_masked(HAPPY_FIELD_ID) is True


def test_each_test_is_given_its_own_register_again():
    """The mask the test above set survived into this one."""
    assert registry().is_masked(HAPPY_FIELD_ID) is False


# ---------------------------------------------------------------------
# The colours
# ---------------------------------------------------------------------


def canonical(colour) -> str:
    """One colour as a full six-digit value, so short forms compare."""
    from PySide6.QtGui import QColor

    app()
    return QColor(colour).name().lower()


def test_the_declared_colours_stay_apart_when_written_in_full():
    """Two declared colours become one when written in full."""
    from src.gui import design_system as ds

    written = {
        name: canonical(value)
        for name, value in {"dot": ds.PRIMARY_BRIGHT, "hover": ds.TEXT_MAX}.items()
    }
    assert len(set(written.values())) == len(written), written
    assert all(len(value) == 7 for value in written.values()), written
    assert ds.PRIMARY_BRIGHT in surface.DOT_STYLE
    assert ds.TEXT_MAX in surface.DOT_STYLE


def test_a_channel_swap_is_reported_where_the_channels_differ():
    """The colour check passes a value with its channels swapped."""
    from src.gui import design_system as ds

    assert canonical(ds.PRIMARY_BRIGHT) == "#00ffee"
    assert canonical("#ee00ff") != canonical(ds.PRIMARY_BRIGHT)
    assert canonical("#00eeff") != canonical(ds.PRIMARY_BRIGHT)


def test_the_hover_white_is_compared_as_text_because_its_channels_are_equal():
    """A colour with three equal channels was left to a colour check.

    ``#ffffff`` reads the same with any two channels swapped, so no colour
    check can report a swap in it. It is compared as exact text instead,
    and a short form and a long form go through one canonical reader.
    """
    from src.gui import design_system as ds

    assert canonical(ds.TEXT_MAX) == "#ffffff"
    assert canonical("#fff") == canonical(ds.TEXT_MAX)
    assert canonical("#888") == "#888888"
    assert f"PrivacyDot:hover {{ color: {ds.TEXT_MAX}; }}" in surface.DOT_STYLE
    old = dot_from_qt(drive_old(BY_NAME["happy"])[0][0])
    new = dot_from_payload(surface.build_view_model(drive_new(BY_NAME["happy"])[0][0]))
    assert new["style_sheet"] == old["style_sheet"]


# ---------------------------------------------------------------------
# The pictures
# ---------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def rebuilt_type():
    """The class a rebuilt dot needs, named for the style selector.

    The style sheet selects by class name, so a dot of any other class is
    painted without its skin.
    """
    from PySide6.QtWidgets import QPushButton

    class PrivacyDot(QPushButton):
        """The rebuilt privacy dot, named for the dot style selector."""

        def __init__(self, parent=None):
            QPushButton.__init__(self, parent)
            self.setAccessibleName("Privacy Dot")

    return PrivacyDot


def model_payload(spec=None):
    """The view model after the same driving, stamped."""
    models, _ = drive_new(spec or BY_NAME["happy"])
    return sealed(surface.build_view_model(models[0]))


def widget_painted_by_the_dot(spec=None):
    """The dot the shipped Qt widget builds, after the same driving."""
    return drive_old(spec or BY_NAME["happy"])[0][0]


def widget_painted_by_the_model(payload, dot_type=None):
    """A dot built only from the payload, never from the shipped widget."""
    payload = unaltered(payload)
    from PySide6.QtCore import Qt

    app()
    focus_policies = {"NoFocus": Qt.NoFocus}
    cursor_shapes = {"PointingHandCursor": Qt.PointingHandCursor}
    dot = (dot_type or rebuilt_type())()
    dot.setFlat(payload["flat"])
    dot.setFocusPolicy(focus_policies[payload["focus_policy"]])
    dot.setCursor(cursor_shapes[payload["cursor_shape"]])
    dot.setText(payload["text"])
    dot.setStyleSheet(payload["style_sheet"])
    dot.setToolTip(payload["tooltip"])
    return dot


PICTURE_SCENARIOS = [
    "happy",
    "built_only_starts_masked",
    "clicked_once",
    "clicked_twice",
    "unicode_field_id",
]


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_two_sides_paint_one_picture(name):
    """The surface painted a different dot than the shipped widget."""
    app()
    note = "%s, %s" % (name, "real fonts" if has_real_fonts() else "no fonts")
    assert_pictures_match(
        old_side=render_offscreen(widget_painted_by_the_dot(BY_NAME[name]), PIXEL_SIZE),
        new_side=render_offscreen(
            widget_painted_by_the_model(model_payload(BY_NAME[name])), PIXEL_SIZE
        ),
        note=note,
    )


def test_the_picture_comparison_can_report_a_difference():
    """The picture check passes whatever the second side paints.

    Two real inputs, one taken from each side: the shipped dot, whose class
    name is what the style sheet selects, and a dot rebuilt from the same
    payload under the plain Qt class, which the same style sheet does not
    reach. The first paints its cyan glyph, the second does not.
    """
    app()
    from PySide6.QtWidgets import QPushButton

    assert "PrivacyDot {" in surface.DOT_STYLE
    assert_pictures_differ(
        old_side=render_offscreen(widget_painted_by_the_dot(), PIXEL_SIZE),
        new_side=render_offscreen(
            widget_painted_by_the_model(model_payload(), dot_type=QPushButton),
            PIXEL_SIZE,
        ),
        note="the named class against the plain Qt one",
    )


@skip_unless_real_fonts
def test_the_two_glyphs_paint_different_pictures():
    """The picture check cannot tell a masked dot from a revealed one.

    Two real inputs, one from each side: the shipped dot on a masked field,
    and a dot rebuilt from the revealed payload. With a font database the
    two glyphs paint different pixels; with none they do not, which is why
    this claim carries the shared guard.
    """
    app()
    assert_pictures_differ(
        old_side=render_offscreen(
            widget_painted_by_the_dot(BY_NAME["clicked_once"]), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            widget_painted_by_the_model(model_payload(BY_NAME["happy"])), PIXEL_SIZE
        ),
        note="a masked dot against a revealed one",
    )


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_painted_dot_shows_more_than_one_colour(name):
    """The two sides matched because the dot painted one flat colour."""
    app()
    from PySide6.QtGui import QColor

    for image in (
        render_offscreen(widget_painted_by_the_dot(BY_NAME[name]), PIXEL_SIZE),
        render_offscreen(
            widget_painted_by_the_model(model_payload(BY_NAME[name])), PIXEL_SIZE
        ),
    ):
        assert image.width() == PIXEL_SIZE[0]
        assert image.height() == PIXEL_SIZE[1]
        seen = set()
        for x in range(image.width()):
            for y in range(image.height()):
                seen.add(QColor(image.pixelColor(x, y)).name())
        assert len(seen) > 1, f"{name} painted one colour, so no change could show"


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, which measures the host's fonts."""
    app()
    stamped = model_payload()
    stamped["text"] = "MOVED"
    with pytest.raises(AssertionError) as reported:
        widget_painted_by_the_model(stamped)
    assert "altered after it came off" in str(reported.value)
    with pytest.raises(AssertionError):
        widget_painted_by_the_model(surface.build_view_model())


def dot_width(text) -> int:
    """The width a label carrying `text` asks for, in the application font.

    The dot's style sheet names a size and no family, so the measurement is
    taken in the general application font rather than in a face the widget
    chose for itself.
    """
    from PySide6.QtWidgets import QLabel

    assert "font-family" not in surface.DOT_STYLE
    return QLabel(text).sizeHint().width()


@skip_unless_no_fonts
def test_two_strings_of_one_length_measure_one_width():
    """With no font database a glyph still carries its own width.

    Every family resolves to a box font advancing one em per character, so
    two glyphs of one length reach the same pixels and only the exact text
    tells them apart.
    """
    app()
    assert len(NARROW_TEXT) == len(WIDE_TEXT)
    assert dot_width(NARROW_TEXT) == dot_width(WIDE_TEXT)


@skip_unless_real_fonts
def test_two_strings_of_one_length_measure_different_widths():
    """With a font database every glyph still advances one em."""
    app()
    assert len(NARROW_TEXT) == len(WIDE_TEXT)
    assert dot_width(NARROW_TEXT) != dot_width(WIDE_TEXT)


# ---------------------------------------------------------------------
# What a picture cannot see, read off both sides instead
# ---------------------------------------------------------------------


def test_the_values_no_picture_carries_are_read_off_both_sides():
    """A value that reaches no pixel was left to the render to report.

    The tooltip, the field id, the flat setting, the focus rule and the
    cursor shape paint nothing at 40 by 40. Each is read off the shipped
    dot and off the surface directly, not through a picture.
    """
    app()
    unpainted = ("tooltip", "field_id", "flat", "focus_policy", "cursor_shape")
    for name in ("happy", "clicked_once", "unicode_field_id", "empty_field_id"):
        old = dot_from_qt(drive_old(BY_NAME[name])[0][0])
        new = dot_from_payload(surface.build_view_model(drive_new(BY_NAME[name])[0][0]))
        for key in unpainted:
            assert new[key] == old[key], (name, key, old[key], new[key])
        assert old["flat"] is True
        assert old["focus_policy"] == "NoFocus"
        assert old["cursor_shape"] == "PointingHandCursor"


def test_the_glyph_is_compared_as_exact_text_on_both_sides():
    """The two glyphs were left to a picture, which cannot always separate them.

    Whether a picture separates the masked glyph from the revealed one
    depends on the host's fonts, so both are read as exact text off each
    side instead.
    """
    revealed = dot_from_qt(drive_old(BY_NAME["happy"])[0][0])
    masked = dot_from_qt(drive_old(BY_NAME["clicked_once"])[0][0])
    assert revealed["text"] == "●"
    assert masked["text"] == "○"
    assert revealed["text"] != masked["text"]
    assert surface.REVEALED_GLYPH == revealed["text"]
    assert surface.MASKED_GLYPH == masked["text"]


# ---------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------


def bridge_answer(params, request_id=1):
    from src.core import desktop_bridge

    return desktop_bridge.handle_line(
        json.dumps({"id": request_id, "method": surface.METHOD, "params": params}),
        desktop_bridge.build_registry(),
    )


def test_the_bridge_registers_the_privacy_dot_method():
    """The renderer cannot reach the privacy dot over the bridge."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()
    assert surface.METHOD in registered
    assert surface.METHOD == "privacy_dot.state"
    answer = bridge_answer({})
    assert answer["ok"] is True
    result = answer["result"]
    assert result["field_id"] == surface.DEFAULT_FIELD_ID
    assert result["style_sheet"] == surface.DOT_STYLE


def test_the_bridge_renders_the_field_it_is_given():
    """The bridge ignored the field the request named."""
    result = bridge_answer({"field_id": "kpi.locked"})["result"]
    assert result["field_id"] == "kpi.locked"
    assert result["text"] == surface.REVEALED_GLYPH
    assert result["tooltip"] == "kpi.locked: " + surface.REVEALED_STATE


def test_the_bridge_clicks_the_dot_as_many_times_as_it_is_asked():
    """The bridge dropped the clicks the request carried."""
    once = bridge_answer({"field_id": "kpi.mature", "clicks": 1})["result"]
    assert once["text"] == surface.MASKED_GLYPH
    assert once["masked"] is True
    registry().set_all(False)
    twice = bridge_answer({"field_id": "kpi.mature", "clicks": 2})["result"]
    assert twice["text"] == surface.REVEALED_GLYPH
    assert twice["calls"].count(surface.CLICKED) == 2


def test_the_bridge_reports_a_request_it_cannot_render():
    """A request the dot refuses came back as an answer."""
    answer = bridge_answer({"field_id": "kpi.exch", "clicks": "lots"})
    assert answer["ok"] is False
    assert answer["error"]["type"] == "ValueError"


def test_the_bridge_answer_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    answer = bridge_answer({"field_id": UNICODE_TEXT, "clicks": 1, "refresh": True})
    encoded = json.loads(json.dumps(answer))
    assert encoded["ok"] is True
    assert encoded["result"]["method"] == surface.METHOD
    assert encoded["result"]["field_id"] == UNICODE_TEXT


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'privacy_dot.state', 'params':"
    " {'field_id': 'kpi.locked', 'clicks': 1}}),"
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
    """Reaching the privacy dot pulled Qt into the backend."""
    answered = run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    assert answered["frame"]["result"]["text"] == surface.MASKED_GLYPH


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True
