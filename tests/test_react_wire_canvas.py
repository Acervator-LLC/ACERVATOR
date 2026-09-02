"""The React wire sheet, against the wire canvas surface it is drawn from."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import theme_engine_surface as tes
from src.gui.main_tabs import wire_canvas_surface as wcs
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    new_engine,
    swap_module,
)

MODULE_PATH = REPO_ROOT / "src" / "gui" / "web" / "wire_canvas.js"
TOKENS_PATH = REPO_ROOT / "src" / "gui" / "web" / "design_tokens.js"
THEMES_PATH = REPO_ROOT / "src" / "gui" / "web" / "theme_engine.js"
WIDGETS_PATH = REPO_ROOT / "src" / "gui" / "web" / "shared_widgets.js"
HEADER_PATH = REPO_ROOT / "src" / "gui" / "web" / "header_strip.js"
SHIPPED_PATH = REPO_ROOT / "src" / "gui" / "visualizer" / "wire_canvas.py"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body writes into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 2

JS_TYPE_OF = {
    "str": "string",
    "int": "number",
    "float": "number",
    "bool": "boolean",
    "tuple": "object",
    "list": "object",
    "dict": "object",
    "NoneType": "null",
}

MOUNT_OPERATIONS = (wcs.DRAW_PATH, wcs.DRAW_POLYGON, wcs.DRAW_LINE)

WIRES: list = [
    {"source_id": "alpha", "target_id": "bravo", "pct": 40, "phase": 0.0},
    {"source_id": "bravo", "target_id": "charlie", "pct": 60, "phase": 1.0},
]
CENTRES: dict = {
    "alpha": [40.0, 40.0],
    "bravo": [200.0, 120.0],
    "charlie": [360.0, 40.0],
}
ADVANCES = {"40%": 24, "60%": 24}

WIRED_TAB: dict = {"wires": WIRES, "bot_centers": CENTRES}


def dragging(**extra: Any) -> dict:
    tab: dict = dict(WIRED_TAB)
    tab["dragging_wire"] = True
    tab["wire_start_id"] = "alpha"
    tab["wire_mouse_pos"] = [300.0, 300.0]
    tab.update(extra)
    return tab


#: The states the sheet opens in, each driven through the bridge handler.
STATES: dict = {
    "empty": {"tab": {}},
    "wires": {"tab": WIRED_TAB, "advances": ADVANCES},
    "skipped": {
        "tab": {
            "wires": [{"source_id": "alpha", "target_id": "ghost", "pct": 10}],
            "bot_centers": CENTRES,
        }
    },
    "drag_loose": {"tab": dragging(), "advances": ADVANCES},
    "drag_connect": {
        "tab": dragging(
            wire_mouse_pos=[360.0, 40.0], bot_hits={"360.0,40.0": "charlie"}
        ),
        "advances": ADVANCES,
    },
    "drag_disconnect": {
        "tab": dragging(
            wire_mouse_pos=[200.0, 120.0], bot_hits={"200.0,120.0": "bravo"}
        ),
        "advances": ADVANCES,
    },
    "dim": {"tab": dict(WIRED_TAB, wire_opacity_pct=40), "advances": ADVANCES},
    "ocean": {"tab": dict(WIRED_TAB, theme_key="ocean"), "advances": ADVANCES},
}
STATE_NAMES = tuple(STATES)
DRAWING_STATES = tuple(one for one in STATE_NAMES if one not in ("empty", "skipped"))


def bridge_payload(**params: Any) -> dict:
    """The surface's answer after one round trip through the bridge's JSON."""
    return json.loads(json.dumps(wcs.view_model(params), ensure_ascii=True))


def state_payload(name: str) -> dict:
    return bridge_payload(**STATES[name])


def tab_with_pcts(first: Any, second: Any) -> dict:
    return {
        "wires": [dict(WIRES[0], pct=first), dict(WIRES[1], pct=second)],
        "bot_centers": CENTRES,
    }


def token_payload() -> dict:
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


def theme_payload() -> dict:
    return json.loads(json.dumps(tes.view_model({}), ensure_ascii=True))


class JsRuntime(JsEngine):
    """A QJSEngine holding wire_canvas.js, wrapped as a JsRuntime."""

    module_path = MODULE_PATH
    setter = "acervatorSetWireCanvas"

    def load_tokens(self) -> None:
        self.run(TOKENS_PATH.read_text(encoding="utf-8"))
        self.bind_json("TOKENS", token_payload())
        self.run("acervatorSetTokens(JSON.parse(TOKENS));")

    def load_themes(self) -> None:
        self.run(THEMES_PATH.read_text(encoding="utf-8"))
        self.bind_json("THEMES", theme_payload())
        self.run("acervatorSetThemes(JSON.parse(THEMES));")

    def load_widgets(self) -> None:
        self.run(WIDGETS_PATH.read_text(encoding="utf-8"))

    def ask(self, expression: str) -> Any:
        return self.json("acervatorWireCanvas." + expression)

    def named(self, method: str, name: Any) -> Any:
        self.bind_json("NAME", name)
        return self.json("acervatorWireCanvas." + method + "(JSON.parse(NAME))")


@pytest.fixture()
def js(qapp) -> JsRuntime:
    assert qapp is not None
    runtime = JsRuntime(new_engine(), HEADER_PATH.read_text(encoding="utf-8"))
    runtime.run(MODULE_SOURCE)
    return runtime


@pytest.fixture()
def resolving(js: JsRuntime) -> JsRuntime:
    js.load_tokens()
    js.load_themes()
    js.load_widgets()
    return js


#: Every published field, and the module expression that answers for it.
MODULE_READERS = {
    name: 'field("' + name + '")' for name in sorted(bridge_payload(tab=WIRED_TAB))
}


def unreachable_fields(payload: dict) -> list:
    return sorted(set(payload) - set(MODULE_READERS))


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    missing = unreachable_fields(payload)
    assert not missing, f"{len(missing)} published fields have no reader: {missing}"
    extra = sorted(set(MODULE_READERS) - set(payload))
    assert not extra, f"the module reads fields the surface has none of: {extra}"
    differing = {
        name: (payload[name], js.ask(reader))
        for name, reader in MODULE_READERS.items()
        if js.ask(reader) != payload[name]
    }
    assert not differing, (
        f"{state}: {len(differing)} of {len(payload)} published fields differ: "
        f"{sorted(differing)}"
    )
    assert len(MODULE_READERS) == len(payload)


def test_the_payload_check_names_a_field_only_the_surface_holds():
    payload = dict(bridge_payload(tab=WIRED_TAB))
    payload["a_field_only_the_surface_holds"] = []
    assert unreachable_fields(payload) == ["a_field_only_the_surface_holds"]


def test_the_payload_check_names_a_field_only_the_module_reads():
    payload = dict(bridge_payload(tab=WIRED_TAB))
    dropped = payload.pop("drawing_calls")
    assert dropped is not None
    assert sorted(set(MODULE_READERS) - set(payload)) == ["drawing_calls"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_the_held_count_apart(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    report = js.push(payload)
    assert report["counts"]["declared"] == len(MODULE_READERS)
    assert report["counts"]["held"] == len(payload)
    assert report["counts"]["operations"] == len(payload["drawing_calls"])
    assert report["counts"]["wires"] == len(payload["tab"]["wires"])
    assert report["counts"]["drawn"] == payload["paint_branches"].count("wire.drawn")


def test_a_missing_field_shortens_the_held_count_and_is_named(js: JsRuntime):
    payload = state_payload("wires")
    del payload["glow"]
    report = js.push(payload)
    assert report["counts"]["declared"] == len(MODULE_READERS)
    assert report["counts"]["held"] == len(MODULE_READERS) - 1
    assert js.ask("unreachable()") == ["glow"]
    assert "glow" in [one["field"] for one in report["faults"]], report["faults"]


def test_a_payload_that_is_not_an_object_is_refused_and_named(js: JsRuntime):
    js.bind_json("PAYLOAD", [])
    report = js.json("acervatorSetWireCanvas(JSON.parse(PAYLOAD))")
    assert report["held"] is None
    assert [one["fault"] for one in report["faults"]] == ["not_an_object"]
    assert js.ask("isLoaded()") is False


MODULE_LITERALS = js_literals(MODULE_SOURCE)


def as_css(value: Any) -> set:
    printed = str(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return {printed}
    return {printed, printed + "px"}


def sheet_values() -> set:
    """Every colour, size and text the sheet paints, in every CSS spelling."""
    found: set = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for one in node.values():
                walk(one)
            return
        if isinstance(node, (list, tuple)):
            for one in node:
                walk(one)
            return
        if isinstance(node, (int, float)) and not isinstance(node, bool):
            found.update(as_css(node))

    for state in STATE_NAMES:
        payload = state_payload(state)
        for name in (
            "drawing_calls",
            "theme",
            "glow",
            "pulse",
            "badge",
            "font",
            "drag",
        ):
            walk(payload[name])
        found.add(payload["style_sheet"])
        found.add(payload["font"]["family"])
        for one in payload["drawing_calls"]:
            if one[0] == wcs.DRAW_TEXT:
                found.add(one[-1])
    found.discard("")
    return found


def token_values() -> set:
    found: set = set()
    for value in dss.TOKENS.values():
        found |= as_css(value)
    for theme in tes.THEMES.values():
        for value in theme.values():
            found |= as_css(value)
    found.discard("")
    return found


SHEET_VALUES = sheet_values()
TOKEN_VALUES = token_values()


def published_names() -> set:
    """Every key and every published name a module is allowed to spell."""
    payload = bridge_payload(tab=WIRED_TAB, advances=ADVANCES)
    found: set = set()

    def keys(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                found.add(key)
                keys(value)
            return
        if isinstance(node, list):
            for one in node:
                keys(one)

    keys(payload)
    for name in ("draw_call_names", "paint_branch_names", "route_names", "event_kinds"):
        found |= set(payload[name])
    found |= set(payload["theme"]["keys"]) | set(payload["theme"]["color_names"])
    found |= set(payload["pens"].values()) | {payload["alignment"]["name"]}
    found |= set(payload["curve"]["element_names"]) | set(payload["buttons"])
    found |= set(payload["cursors"]) | {payload["accessible_name"]}
    return found


PUBLISHED_NAMES = published_names()
NAMED_WORDS = sorted(set(MODULE_LITERALS["strings"]) & PUBLISHED_NAMES)


def test_the_module_writes_no_number():
    assert not MODULE_LITERALS[
        "numbers"
    ], f"wire_canvas.js holds numeric literals: {MODULE_LITERALS['numbers']}"


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"wire_canvas.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_sheet_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & SHEET_VALUES)
    assert not written, f"wire_canvas.js spells out sheet values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"wire_canvas.js spells out token values: {written}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        "wire_canvas.js holds a slash outside a comment, which the literal "
        f"scan cannot read: {MODULE_LITERALS['slashes']}"
    )


def test_every_published_word_the_module_names_is_a_name_and_not_a_value():
    assert NAMED_WORDS, "the module names no published word, so the scan read nothing"
    overlap = sorted(set(NAMED_WORDS) & SHEET_VALUES)
    assert not overlap, f"these named words are values the sheet paints: {overlap}"


def test_the_module_spells_no_published_string_that_is_not_a_name():
    written = set(MODULE_LITERALS["strings"])
    published = {
        one for one in written if one in SHEET_VALUES or one in PUBLISHED_NAMES
    }
    assert published - PUBLISHED_NAMES == set(), sorted(published - PUBLISHED_NAMES)


PLANTED_LINES = {
    "colour": 'var written = "#00ffcc";',
    "size": 'var written = "' + str(wcs.BADGE_HEIGHT_PX) + 'px";',
    "alpha": "var written = " + str(wcs.OPAQUE_ALPHA) + ";",
    "number": "var written = 12;",
    "label": 'var written = "' + wcs.LABEL_FORMAT.format(pct=WIRES[0]["pct"]) + '";',
    "font": 'var written = "' + wcs.FONT_FAMILY + '";',
    "style_sheet": 'var written = "' + wcs.CANVAS_STYLE + '";',
    "token_value": 'var written = "' + str(dss.PRIMARY) + '";',
    "regex": "var written = /ab+c/;",
}


def caught_by_scan(source: str) -> set:
    found = js_literals(source)
    strings = set(found["strings"])
    caught = set()
    if found["numbers"]:
        caught.add("number")
    if HEX_COLOUR.findall(source):
        caught.add("colour")
    if strings & SHEET_VALUES:
        caught.add("sheet_value")
    if strings & TOKEN_VALUES:
        caught.add("token_value")
    if found["slashes"]:
        caught.add("regex")
    return caught


@pytest.mark.parametrize("kind", sorted(PLANTED_LINES))
def test_the_literal_scan_names_one_written_value_at_a_time(kind: str):
    caught = caught_by_scan(PLANTED_LINES[kind])
    assert caught, f"the scan reported nothing on the written {kind}"


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    found = js_literals('// #00ffcc\nvar kept = "kept";')
    assert found["strings"] == ["kept"]
    assert not found["numbers"]


def test_each_written_value_is_caught_in_the_shipped_module_file():
    """Each value is written into the real file, caught, then the file is put back."""
    original = MODULE_PATH.read_bytes()
    before = hashlib.sha256(original).hexdigest()
    assert original.decode("utf-8") == MODULE_SOURCE
    caught_each = {}
    try:
        for kind in sorted(PLANTED_LINES):
            swap_module(MODULE_PATH, original + PLANTED_LINES[kind].encode("utf-8"))
            caught_each[kind] = caught_by_scan(MODULE_PATH.read_text(encoding="utf-8"))
            swap_module(MODULE_PATH, original)
            after = hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()
            assert after == before, f"the file was not restored after the {kind} write"
    finally:
        swap_module(MODULE_PATH, original)
    quiet = sorted(kind for kind, caught in caught_each.items() if not caught)
    assert not quiet, f"the scan reported nothing on these writes in the file: {quiet}"
    assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before


def test_the_changed_file_is_still_a_module_the_page_can_run(js: JsRuntime):
    for kind, line in sorted(PLANTED_LINES.items()):
        runtime = JsRuntime(js.engine_of(), MODULE_SOURCE + line)
        assert runtime.json("typeof acervatorSetWireCanvas") == "function", kind


def python_kinds(payload: Any) -> dict:
    """The JavaScript type of every value of ``payload``, by dotted path."""
    found: dict = {}

    def descend(path: str, value: Any) -> None:
        found[path] = JS_TYPE_OF[type(value).__name__]
        if isinstance(value, dict):
            for key, inner in value.items():
                descend(path + "." + str(key), inner)
            return
        if isinstance(value, (list, tuple)):
            for at, inner in enumerate(value):
                descend(path + "." + str(at), inner)

    descend("", payload)
    return found


def js_kinds_of(js: JsRuntime, name: str) -> dict:
    js.bind_json("FIELD", name)
    return js.json(
        "(function () {"
        "  var found = {};"
        "  var walk = function (path, value) {"
        "    found[path] = value === null ? 'null' : typeof value;"
        "    if (value === null || typeof value !== 'object') { return; }"
        "    Object.keys(value).forEach(function (key) {"
        "      walk(path + '.' + key, value[key]); });"
        "  };"
        "  walk('', acervatorWireCanvas.field(JSON.parse(FIELD)));"
        "  return found; })()"
    )


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_value_of_every_state_arrives_as_the_type_it_left_as(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    sent = python_kinds(payload)
    seen = {"": "object"}
    for name in sorted(payload):
        for tail, kind in js_kinds_of(js, name).items():
            seen["." + name + tail] = kind
    differing = {
        path: (sent[path], seen.get(path))
        for path in sent
        if seen.get(path) != sent[path]
    }
    assert not differing, (
        f"{state}: {len(differing)} of {len(sent)} values changed type: "
        f"{dict(sorted(differing.items())[:8])}"
    )
    assert len(sent) > len(payload), "the walk never reached a leaf"


def test_the_type_walk_names_a_scalar_where_a_list_was_published():
    sent = python_kinds({"wires": [1, 2]})
    scalar = python_kinds({"wires": 1})
    assert sent[".wires"] == "object" and scalar[".wires"] == "number"
    assert ".wires.0" in sent and ".wires.0" not in scalar


def test_the_type_walk_names_a_null_where_a_bag_was_published():
    sent = python_kinds({"bot_centers": {"alpha": [1.0, 2.0]}})
    empty = python_kinds({"bot_centers": None})
    assert sent[".bot_centers"] == "object" and empty[".bot_centers"] == "null"
    assert ".bot_centers.alpha" in sent and ".bot_centers.alpha" not in empty


def test_the_type_check_names_one_value_that_changed_shape(js: JsRuntime):
    payload = state_payload("wires")
    payload["glow"] = [[name, value] for name, value in payload["glow"].items()]
    js.push(payload)
    seen = js_kinds_of(js, "glow")
    assert seen.get(".alpha") is None, "a list reached the module as a bag"
    assert seen.get(".0") == "object"


@pytest.mark.parametrize("state", DRAWING_STATES)
def test_the_module_counts_the_same_operations_the_surface_wrote(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    written = payload["drawing_calls"]
    assert js.ask("mountedOps()") == [
        one[0] for one in written if one[0] in MOUNT_OPERATIONS
    ]
    assert js.ask("cssOps()") == {
        "dots": sum(one[0] == wcs.DRAW_ELLIPSE for one in written),
        "plates": sum(one[0] == wcs.DRAW_ROUNDED_RECT for one in written),
        "labels": sum(one[0] == wcs.DRAW_TEXT for one in written),
    }


def test_the_operation_count_check_names_a_dropped_curve(js: JsRuntime):
    payload = state_payload("wires")
    payload["drawing_calls"] = [
        one for one in payload["drawing_calls"] if one[0] != wcs.DRAW_PATH
    ]
    js.push(payload)
    assert wcs.DRAW_PATH not in js.ask("mountedOps()")
    assert js.ask("cssOps()")["labels"] == len(payload["tab"]["wires"])


@pytest.mark.parametrize("state", DRAWING_STATES)
def test_the_module_names_the_drag_branch_the_surface_recorded(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    written = [one for one in payload["paint_branches"] if one.startswith("drag.")]
    assert js.ask("dragBranch()") == (written[-1] if written else None)


def test_the_drag_branch_check_reads_a_sheet_with_no_drag_as_none(js: JsRuntime):
    js.push(state_payload("wires"))
    assert js.ask("dragBranch()") is None
    js.push(state_payload("drag_loose"))
    assert js.ask("dragBranch()") == "drag.loose"


@pytest.mark.parametrize("state", DRAWING_STATES)
def test_the_alpha_of_every_published_colour_is_scaled_to_a_fraction(
    js: JsRuntime, state: str
):
    js.push(state_payload(state))
    colours = wcs.theme(STATES[state]["tab"].get("theme_key", wcs.THEME_FALLBACK_KEY))
    for name, value in sorted(colours.items()):
        red, green, blue, alpha = value
        assert js.named("rgba", list(value)) == rgba_of([red, green, blue, alpha]), name


def test_the_alpha_scaling_check_names_a_byte_alpha_left_unscaled(js: JsRuntime):
    js.push(state_payload("wires"))
    full = js.named("rgba", [0, 0, 0, wcs.OPAQUE_ALPHA])
    part = js.named("rgba", [0, 0, 0, wcs.GLOW_ALPHA])
    assert full.endswith(", 1)"), full
    assert part.endswith(f", {js_number(wcs.GLOW_ALPHA * wcs.ALPHA_UNIT)})"), part
    assert str(wcs.GLOW_ALPHA) != part.split(", ")[-1].rstrip(")")


def test_the_alpha_unit_the_surface_publishes_is_the_reciprocal_of_its_scale():
    payload = bridge_payload(tab=WIRED_TAB)
    assert payload["theme"]["alpha_scale"] == float(payload["theme"]["opaque_alpha"])
    assert payload["theme"]["alpha_unit"] * payload["theme"]["alpha_scale"] == 1.0


def test_a_colour_written_as_swapped_hex_is_named_by_the_visualizer(js: JsRuntime):
    js.push(state_payload("wires"))
    assert js.named("qtColour", "#80ff0000") is None
    assert "not_loaded" in [one["fault"] for one in js.ask("faults()")]


class Browser:
    """The real renderer page in a Chromium view, driven through this Browser."""

    def __init__(self) -> None:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        self.open_page()
        self.wait_for_module()

    def open_page(self) -> None:
        """Loads the renderer page and waits until its load finishes."""
        from PySide6.QtCore import QEventLoop, QTimer, QUrl

        loop = QEventLoop()
        box: dict = {}

        def _loaded(ok: bool) -> None:
            box.setdefault("ok", ok)
            loop.quit()

        connection = self._view.loadFinished.connect(_loaded)
        self._view.load(QUrl.fromLocalFile(str(INDEX_HTML)))
        QTimer.singleShot(JS_TIMEOUT_MS, loop.quit)
        loop.exec()
        self._view.loadFinished.disconnect(connection)
        assert box.get("ok") is True, f"{INDEX_HTML.name} did not load: {box}"

    def wait_for_module(self) -> None:
        for attempt in range(PAGE_ATTEMPTS):
            if attempt:
                self.open_page()
            for _ in range(READY_ROUNDS):
                if self.js("typeof window.acervatorSetWireCanvas") == "function":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the wire module: readyState "
            + str(self.js("document.readyState"))
            + ", scripts "
            + str(self.js("document.scripts.length"))
            + ", tokens "
            + str(self.js("typeof window.acervatorSetTokens"))
        )

    def js(self, script: str) -> Any:
        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        box: dict = {}

        def _answered(value: Any) -> None:
            box.setdefault("v", value)
            loop.quit()

        self._view.page().runJavaScript(script, _answered)
        QTimer.singleShot(JS_TIMEOUT_MS, loop.quit)
        loop.exec()
        assert "v" in box, "the browser never answered: " + script[:80]
        return box["v"]

    def parsed(self, expression: str) -> Any:
        return json.loads(self.js("JSON.stringify(" + expression + ")"))

    def settle(self, milliseconds: int) -> None:
        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        QTimer.singleShot(milliseconds, loop.quit)
        loop.exec()

    def close(self) -> None:
        self._view.deleteLater()


@pytest.fixture()
def browser(qapp):
    assert qapp is not None
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    page = Browser()
    yield page
    page.close()


#: The style names read off every drawn part.
STYLE_NAMES = [
    "position",
    "display",
    "alignItems",
    "justifyContent",
    "left",
    "top",
    "width",
    "height",
    "opacity",
    "borderTopLeftRadius",
    "backgroundColor",
    "backgroundImage",
    "color",
    "fontSize",
    "fontWeight",
    "whiteSpace",
    "pointerEvents",
    "boxSizing",
]

PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "document.body.appendChild(window.HOST);"
    "window.readStyle = function (el, names) {"
    "  var computed = getComputedStyle(el);"
    "  var found = {};"
    "  names.forEach(function (n) { found[n] = computed[n]; });"
    "  return found; };"
    "window.probeStyle = function (cssText, names) {"
    "  var probe = document.createElement('div');"
    "  probe.style.cssText = cssText;"
    "  document.body.appendChild(probe);"
    "  var found = window.readStyle(probe, names);"
    "  probe.remove();"
    "  return found; };"
)

WATCH_VIOLATIONS = (
    "window.VIOLATIONS = [];"
    "document.addEventListener('securitypolicyviolation', function (e) {"
    "  window.VIOLATIONS.push(e.violatedDirective + ' ' + e.blockedURI); });"
)

READ_PARTS = (
    "(function () {"
    "  var names = JSON.parse(window.STYLE_NAMES);"
    "  var found = [];"
    "  var walk = function (el, path) {"
    "    var part = el.getAttribute('data-part');"
    "    var here = path;"
    "    if (part !== null) {"
    "      here = path ? path + '/' + part : part;"
    "      var attrs = {};"
    "      Array.prototype.slice.call(el.attributes).forEach(function (a) {"
    "        attrs[a.name] = a.value; });"
    "      var own = '';"
    "      Array.prototype.slice.call(el.childNodes).forEach(function (n) {"
    "        if (n.nodeType === Node.TEXT_NODE) { own += n.nodeValue; } });"
    "      found.push({ path: here, tag: el.tagName, attrs: attrs,"
    "        text: own, style: window.readStyle(el, names) });"
    "    }"
    "    Array.prototype.slice.call(el.children).forEach(function (child) {"
    "      walk(child, here); });"
    "  };"
    "  if (window.HOST.firstChild) { walk(window.HOST.firstChild, ''); }"
    "  return JSON.stringify(found); })()"
)


def give_tokens(browser: Browser) -> int:
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    written = browser.parsed(
        "(function () {"
        "  acervatorSetTokens(JSON.parse(window.TOKENS));"
        "  return acervatorTokens.apply(document.documentElement); })()"
    )
    assert written, "no design token reached the page's stylesheet"
    return len(written)


def draw_sheet(browser: Browser, payload: dict) -> list:
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorWireCanvas.forget();"
        "acervatorSetWireCanvas(JSON.parse(window.PAYLOAD));"
        "acervatorWireCanvas.renderSheet(window.HOST);"
    )
    return json.loads(browser.js(READ_PARTS))


def probe(browser: Browser, body: str, names: list) -> dict:
    return browser.parsed(
        "window.probeStyle(" + json.dumps(body) + ", " + json.dumps(sorted(names)) + ")"
    )


def at_path(parts: list, path: str) -> list:
    return [one for one in parts if one["path"] == path]


def only(parts: list, path: str) -> dict:
    found = at_path(parts, path)
    assert len(found) == 1, f"{len(found)} parts at {path}"
    return found[0]


def by_key(parts: list, path: str, key: str) -> dict:
    found = [one for one in at_path(parts, path) if one["attrs"].get("data-key") == key]
    assert len(found) == 1, f"{len(found)} parts at {path} named {key}"
    return found[0]


def js_number(value: Any) -> str:
    """One number spelled the way JavaScript spells it."""
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value)


def rgba_of(value: list) -> str:
    red, green, blue, alpha = value
    return f"rgba({red}, {green}, {blue}, {js_number(alpha * wcs.ALPHA_UNIT)})"


def calls_of(payload: dict, name: str) -> list:
    return [one for one in payload["drawing_calls"] if one[0] == name]


def badge_declaration(payload: dict, at: int) -> str:
    plate = calls_of(payload, wcs.DRAW_ROUNDED_RECT)[at]
    box = plate[1]
    return (
        "position:absolute;box-sizing:border-box;display:flex;"
        "align-items:center;justify-content:center;"
        f"left:{box[0]}px;top:{box[1]}px;width:{box[2]}px;height:{box[3]}px;"
        f"border-radius:{plate[2]}px;"
        f"background:{rgba_of(payload['badge']['fill'])}"
    )


def pulse_declaration(payload: dict, at: int) -> str:
    dot = calls_of(payload, wcs.DRAW_ELLIPSE)[at]
    centre = dot[1]
    return (
        "position:absolute;"
        f"left:{centre[0] - dot[2]}px;top:{centre[1] - dot[3]}px;"
        f"width:{dot[2] + dot[2]}px;height:{dot[3] + dot[3]}px;"
        f"border-radius:{dot[2]}px"
    )


BADGE_PROPERTIES = [
    "position",
    "boxSizing",
    "display",
    "alignItems",
    "justifyContent",
    "left",
    "top",
    "width",
    "height",
    "borderTopLeftRadius",
    "backgroundColor",
]
PULSE_PROPERTIES = ["position", "left", "top", "width", "height", "borderTopLeftRadius"]


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    assert browser.js("typeof window.acervatorSetWireCanvas") == "function"
    assert browser.js("typeof window.acervatorWireCanvas.renderSheet") == "function"


def test_the_module_makes_no_network_call_of_its_own(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    drawn = draw_sheet(browser, state_payload("wires"))
    assert drawn, "nothing was drawn, so the check watched an empty page"
    assert browser.parsed("window.VIOLATIONS") == []


@pytest.mark.parametrize("state", DRAWING_STATES)
def test_the_drawn_sheet_holds_one_group_for_every_wire_the_surface_drew(
    browser: Browser, state: str
):
    payload = state_payload(state)
    drawn = draw_sheet(browser, payload)
    groups = at_path(drawn, "wire-sheet/wire")
    assert len(groups) == payload["paint_branches"].count("wire.drawn")


def test_a_skipped_wire_draws_no_group(browser: Browser):
    payload = state_payload("skipped")
    drawn = draw_sheet(browser, payload)
    assert payload["paint_branches"] == ["wire.skipped"]
    assert at_path(drawn, "wire-sheet/wire") == []
    assert len(at_path(drawn, "wire-sheet/wire-mount")) == 1


def test_an_empty_sheet_draws_the_mount_and_nothing_else(browser: Browser):
    drawn = draw_sheet(browser, state_payload("empty"))
    assert [one["path"] for one in drawn] == ["wire-sheet", "wire-sheet/wire-mount"]


@pytest.mark.parametrize("state", DRAWING_STATES)
def test_every_drawn_badge_matches_a_probe_styled_from_the_surface(
    browser: Browser, state: str
):
    payload = state_payload(state)
    drawn = draw_sheet(browser, payload)
    badges = at_path(drawn, "wire-sheet/wire/badge")
    assert badges, "no badge was drawn"
    for at, badge in enumerate(badges):
        expected = probe(browser, badge_declaration(payload, at), BADGE_PROPERTIES)
        differing = {
            name: (value, badge["style"].get(name))
            for name, value in expected.items()
            if badge["style"].get(name) != value
        }
        assert not differing, f"{state} badge {at}: {differing}"


def test_the_badge_check_names_one_changed_corner(browser: Browser):
    payload = state_payload("wires")
    drawn = draw_sheet(browser, payload)
    badge = at_path(drawn, "wire-sheet/wire/badge")[0]
    written = badge_declaration(payload, 0).replace(
        f"border-radius:{wcs.BADGE_CORNER_PX}px",
        f"border-radius:{wcs.BADGE_CORNER_PX + wcs.BADGE_HEIGHT_PX}px",
    )
    expected = probe(browser, written, BADGE_PROPERTIES)
    assert expected["borderTopLeftRadius"] != badge["style"]["borderTopLeftRadius"]


@pytest.mark.parametrize("state", DRAWING_STATES)
def test_every_drawn_pulse_matches_a_probe_styled_from_the_surface(
    browser: Browser, state: str
):
    payload = state_payload(state)
    drawn = draw_sheet(browser, payload)
    dots = at_path(drawn, "wire-sheet/wire/pulse")
    assert dots, "no travelling dot was drawn"
    for at, dot in enumerate(dots):
        expected = probe(browser, pulse_declaration(payload, at), PULSE_PROPERTIES)
        differing = {
            name: (value, dot["style"].get(name))
            for name, value in expected.items()
            if dot["style"].get(name) != value
        }
        assert not differing, f"{state} pulse {at}: {differing}"


def gradient_declaration(payload: dict, at: int) -> str:
    gradient = calls_of(payload, wcs.SET_GRADIENT_BRUSH)[at]
    stops = ", ".join(
        f"{rgba_of(colour)} {js_number(float(stop) * gradient[2])}px"
        for stop, colour in gradient[3]
    )
    return f"background:radial-gradient({stops})"


def test_the_drawn_pulse_carries_the_gradient_the_surface_described(browser: Browser):
    payload = state_payload("wires")
    drawn = draw_sheet(browser, payload)
    dot = at_path(drawn, "wire-sheet/wire/pulse")[0]
    expected = probe(browser, gradient_declaration(payload, 0), ["backgroundImage"])
    assert expected["backgroundImage"] != "none", "the probe carried no gradient"
    assert dot["style"]["backgroundImage"] == expected["backgroundImage"]


def test_the_gradient_check_reads_a_dot_with_no_gradient_as_none(browser: Browser):
    payload = state_payload("wires")
    payload["drawing_calls"] = [
        one for one in payload["drawing_calls"] if one[0] != wcs.SET_GRADIENT_BRUSH
    ]
    drawn = draw_sheet(browser, payload)
    dot = at_path(drawn, "wire-sheet/wire/pulse")[0]
    assert dot["style"]["backgroundImage"] == "none"


@pytest.mark.parametrize("state", DRAWING_STATES)
def test_every_drawn_label_shows_the_text_the_surface_wrote(
    browser: Browser, state: str
):
    payload = state_payload(state)
    drawn = draw_sheet(browser, payload)
    written = [one[-1] for one in calls_of(payload, wcs.DRAW_TEXT)]
    shown = [one["text"] for one in at_path(drawn, "wire-sheet/wire/badge/badge-label")]
    assert shown == written


def test_the_label_check_names_one_changed_percentage(browser: Browser):
    payload = state_payload("wires")
    for one in payload["drawing_calls"]:
        if one[0] == wcs.DRAW_TEXT:
            one[-1] = one[-1] + one[-1]
    drawn = draw_sheet(browser, payload)
    shown = [one["text"] for one in at_path(drawn, "wire-sheet/wire/badge/badge-label")]
    assert shown != [one[-1] for one in calls_of(state_payload("wires"), wcs.DRAW_TEXT)]
    assert shown == [one[-1] for one in calls_of(payload, wcs.DRAW_TEXT)]


def test_the_drawn_label_takes_the_pen_colour_and_the_font_the_surface_wrote(
    browser: Browser,
):
    payload = state_payload("wires")
    drawn = draw_sheet(browser, payload)
    label = at_path(drawn, "wire-sheet/wire/badge/badge-label")[0]
    colours = wcs.theme(wcs.THEME_FALLBACK_KEY)
    written = (
        f"color:{rgba_of(list(colours['accent']))};"
        f"font-size:{wcs.FONT_SIZE_PT}pt;"
        f"font-weight:{wcs.FONT_WEIGHT_VALUE}"
    )
    expected = probe(browser, written, ["color", "fontSize", "fontWeight"])
    differing = {
        name: (value, label["style"].get(name))
        for name, value in expected.items()
        if label["style"].get(name) != value
    }
    assert not differing, differing


def test_the_font_size_check_reads_a_different_point_size_apart(browser: Browser):
    draw_sheet(browser, state_payload("wires"))
    one = probe(browser, f"font-size:{wcs.FONT_SIZE_PT}pt", ["fontSize"])
    two = probe(
        browser, f"font-size:{wcs.FONT_SIZE_PT + wcs.FONT_SIZE_PT}pt", ["fontSize"]
    )
    assert one["fontSize"] != two["fontSize"]


@pytest.mark.parametrize("state", DRAWING_STATES)
def test_the_drawn_sheet_carries_the_opacity_the_surface_set(
    browser: Browser, state: str
):
    payload = state_payload(state)
    drawn = draw_sheet(browser, payload)
    written = calls_of(payload, wcs.SET_OPACITY)[0][1]
    assert only(drawn, "wire-sheet")["style"]["opacity"] == js_number(written)


def test_the_opacity_check_reads_the_dimmed_sheet_apart_from_the_bright_one(
    browser: Browser,
):
    bright = draw_sheet(browser, state_payload("wires"))
    dim = draw_sheet(browser, state_payload("dim"))
    assert only(bright, "wire-sheet")["style"]["opacity"] != (
        only(dim, "wire-sheet")["style"]["opacity"]
    )


def test_the_drawn_sheet_takes_the_qt_style_sheet_the_surface_published(
    browser: Browser,
):
    payload = state_payload("wires")
    drawn = draw_sheet(browser, payload)
    expected = probe(browser, payload["style_sheet"], ["backgroundColor"])
    assert only(drawn, "wire-sheet")["style"]["backgroundColor"] == (
        expected["backgroundColor"]
    )


def test_a_badge_fill_written_as_swapped_hex_paints_nothing_and_is_named(
    browser: Browser,
):
    payload = state_payload("wires")
    for one in payload["drawing_calls"]:
        if one[0] == wcs.SET_BRUSH and one[1] == list(wcs.BADGE_FILL):
            one[1] = "#a0ff0000"
    drawn = draw_sheet(browser, payload)
    badge = at_path(drawn, "wire-sheet/wire/badge")[0]
    assert badge["style"]["backgroundColor"] == "rgba(0, 0, 0, 0)"
    named = [one["fault"] for one in browser.parsed("acervatorWireCanvas.faults()")]
    assert "qt_colour" in named, named


def test_the_swapped_hex_check_keeps_a_colour_css_reads_the_same_way(browser: Browser):
    payload = state_payload("wires")
    for one in payload["drawing_calls"]:
        if one[0] == wcs.SET_BRUSH and one[1] == list(wcs.BADGE_FILL):
            one[1] = "#ff0000"
    drawn = draw_sheet(browser, payload)
    badge = at_path(drawn, "wire-sheet/wire/badge")[0]
    assert badge["style"]["backgroundColor"] == "rgb(255, 0, 0)"
    named = [one["fault"] for one in browser.parsed("acervatorWireCanvas.faults()")]
    assert "qt_colour" not in named, named


def test_the_mount_names_the_operations_no_css_box_can_take(browser: Browser):
    payload = state_payload("drag_loose")
    drawn = draw_sheet(browser, payload)
    mount = only(drawn, "wire-sheet/wire-mount")
    written = [one for one in payload["drawing_calls"] if one[0] in MOUNT_OPERATIONS]
    assert mount["attrs"]["data-ops"] == str(len(written))
    assert mount["attrs"]["data-slot"] == "wire-mount"
    assert mount["attrs"]["data-drag"] == payload["paint_branches"][-1]


def test_the_mount_count_check_names_a_sheet_with_fewer_curves(browser: Browser):
    payload = state_payload("wires")
    full = draw_sheet(browser, payload)
    payload["drawing_calls"] = [
        one for one in payload["drawing_calls"] if one[0] != wcs.DRAW_PATH
    ]
    fewer = draw_sheet(browser, payload)
    assert only(full, "wire-sheet/wire-mount")["attrs"]["data-ops"] != (
        only(fewer, "wire-sheet/wire-mount")["attrs"]["data-ops"]
    )


def test_no_sloped_or_curved_operation_reaches_a_drawn_css_box(browser: Browser):
    payload = state_payload("drag_loose")
    drawn = draw_sheet(browser, payload)
    boxes = [one for one in drawn if one["path"] != "wire-sheet/wire-mount"]
    assert boxes, "nothing was drawn outside the mount"
    for box in boxes:
        assert "rotate" not in json.dumps(box["style"]), box["path"]
    mount = only(drawn, "wire-sheet/wire-mount")
    assert int(mount["attrs"]["data-ops"]) == sum(
        one[0] in MOUNT_OPERATIONS for one in payload["drawing_calls"]
    )


def carriers_of(value: Any) -> list:
    printed = str(value)
    return sorted(
        name
        for name, one in dss.TOKENS.items()
        if str(one) == printed and name not in dss.ALIASES
    )


#: Each value the sheet paints that a token could carry, with the group
#: whose meaning matches it.
TOKEN_CANDIDATES = {
    "corner": (wcs.BADGE_CORNER_PX, "radii"),
    "weight": (wcs.FONT_WEIGHT_VALUE, "weights"),
    "family": (wcs.FONT_FAMILY, "font_families"),
}


@pytest.mark.parametrize("name", sorted(TOKEN_CANDIDATES))
def test_each_value_resolves_to_a_token_only_when_one_name_carries_it(
    resolving: JsRuntime, name: str
):
    resolving.push(state_payload("wires"))
    value, group = TOKEN_CANDIDATES[name]
    resolved = resolving.ask("tokens()").get(name)
    carriers = carriers_of(value)
    matching = [one for one in carriers if one in dss.GROUPS[group]]
    if len(carriers) == 1 and matching:
        assert resolved == carriers[0], f"{name} is carried by {carriers}"
    else:
        assert resolved is None, (
            f"{name} resolved to {resolved} though {len(carriers)} names carry "
            f"{value}: {carriers}"
        )


def test_the_token_resolver_names_a_value_exactly_one_token_carries(
    resolving: JsRuntime,
):
    resolving.push(state_payload("wires"))
    alone = sorted(
        str(one)
        for one in set(dss.GROUPS["radii"].values())
        if len(carriers_of(one)) == 1
    )
    assert alone, "no radius value is carried by exactly one token"
    for value in alone:
        assert resolving.named("variableFor", value) == carriers_of(value)[0]


def test_the_token_resolver_reports_no_name_with_the_widget_module_off_the_page(
    js: JsRuntime,
):
    js.push(state_payload("wires"))
    assert js.named("variableFor", str(wcs.BADGE_CORNER_PX)) is None


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_element_the_sheet_draws_carries_a_part_name(
    browser: Browser, state: str
):
    draw_sheet(browser, state_payload(state))
    every = browser.js("window.HOST.querySelectorAll('*').length")
    named = browser.js("window.HOST.querySelectorAll('[data-part]').length")
    assert every == named, f"{state}: {every - named} drawn elements carry no name"
    assert every >= 2, f"{state}: the page drew {every} elements, so nothing was read"


def test_the_naming_check_names_one_element_added_without_a_part(browser: Browser):
    draw_sheet(browser, state_payload("wires"))
    browser.js("window.HOST.firstChild.appendChild(document.createElement('div'));")
    every = browser.js("window.HOST.querySelectorAll('*').length")
    named = browser.js("window.HOST.querySelectorAll('[data-part]').length")
    assert every - named == 1


@pytest.mark.parametrize("state", DRAWING_STATES)
def test_the_module_names_every_wire_in_the_order_the_surface_published(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    assert js.ask("wireNames()") == payload["tab"]["wire_order"]


def test_the_wire_order_check_names_a_swapped_pair(js: JsRuntime):
    js.push(state_payload("wires"))
    before = js.ask("wireNames()")
    js.push(
        bridge_payload(tab={"wires": list(reversed(WIRES)), "bot_centers": CENTRES})
    )
    assert js.ask("wireNames()") == list(reversed(before))


def test_the_module_names_every_bot_in_the_order_the_surface_published(js: JsRuntime):
    payload = state_payload("wires")
    js.push(payload)
    assert js.ask("botOrder()") == payload["tab"]["bot_center_order"]


def test_a_bag_keyed_by_a_number_arrives_reordered_and_the_published_list_does_not(
    js: JsRuntime,
):
    """The order of a numeric-keyed bag is lost across the bridge, so it is a list."""
    numbered = {
        "wires": [{"source_id": "7", "target_id": "3", "pct": 40}],
        "bot_centers": {"7": [10.0, 10.0], "3": [20.0, 20.0], "1": [30.0, 30.0]},
    }
    payload = bridge_payload(tab=numbered)
    js.push(payload)
    assert list(payload["tab"]["bot_centers"]) == ["7", "3", "1"]
    assert js.json('Object.keys(acervatorWireCanvas.field("tab").bot_centers)') == [
        "1",
        "3",
        "7",
    ]
    assert js.ask("botOrder()") == ["7", "3", "1"]


def test_a_bag_keyed_by_a_name_keeps_its_order_across_the_bridge(js: JsRuntime):
    payload = state_payload("wires")
    js.push(payload)
    assert js.json('Object.keys(acervatorWireCanvas.field("tab").bot_centers)') == list(
        payload["tab"]["bot_centers"]
    )


def test_the_bot_order_check_names_a_payload_with_no_published_list(js: JsRuntime):
    payload = state_payload("wires")
    del payload["tab"]["bot_center_order"]
    js.push(payload)
    assert js.ask("botOrder()") == []
    assert "bot_center_order" in [one["field"] for one in js.ask("faults()")]


def test_the_module_answers_one_wire_by_its_name_and_not_by_its_place(js: JsRuntime):
    payload = state_payload("wires")
    js.push(payload)
    for name in payload["tab"]["wire_order"]:
        found = js.named("wireAt", name)
        assert found["key"] == name
        assert name.startswith(str(found["source"]))
        assert name.endswith(str(found["target"]))


def test_the_identity_check_names_two_wires_whose_values_were_swapped(js: JsRuntime):
    first, second = WIRES[0]["pct"], WIRES[1]["pct"]
    js.push(bridge_payload(tab=tab_with_pcts(first, second), advances=ADVANCES))
    names = js.ask("wireNames()")
    before = {name: js.named("wireAt", name)["written"] for name in names}
    js.push(bridge_payload(tab=tab_with_pcts(second, first), advances=ADVANCES))
    after = {name: js.named("wireAt", name)["written"] for name in names}
    changed = sorted(name for name in before if before[name] != after[name])
    assert changed == sorted(names), f"only {changed} of {names} were named as changed"


def test_the_identity_check_is_quiet_when_no_value_moved(js: JsRuntime):
    first, second = WIRES[0]["pct"], WIRES[1]["pct"]
    js.push(bridge_payload(tab=tab_with_pcts(first, second), advances=ADVANCES))
    names = js.ask("wireNames()")
    before = {name: js.named("wireAt", name)["written"] for name in names}
    js.push(bridge_payload(tab=tab_with_pcts(first, second), advances=ADVANCES))
    after = {name: js.named("wireAt", name)["written"] for name in names}
    assert before == after


def test_the_drawn_groups_name_their_two_bots(browser: Browser):
    payload = state_payload("wires")
    drawn = draw_sheet(browser, payload)
    for wire in payload["tab"]["wires"]:
        name = wire["source_id"] + "->" + wire["target_id"]
        group = by_key(drawn, "wire-sheet/wire", name)
        assert group["attrs"]["data-source"] == wire["source_id"]
        assert group["attrs"]["data-target"] == wire["target_id"]


def test_a_reordered_payload_moves_the_drawn_group_and_the_check_names_it(
    browser: Browser,
):
    before = [
        one["attrs"]["data-key"]
        for one in at_path(
            draw_sheet(browser, state_payload("wires")), "wire-sheet/wire"
        )
    ]
    swapped = bridge_payload(
        tab={"wires": list(reversed(WIRES)), "bot_centers": CENTRES}, advances=ADVANCES
    )
    after = [
        one["attrs"]["data-key"]
        for one in at_path(draw_sheet(browser, swapped), "wire-sheet/wire")
    ]
    assert after == list(reversed(before))


MARKUP = '<img src="x.png">'


def test_a_percentage_carrying_markup_is_drawn_as_characters(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    payload = bridge_payload(
        tab={
            "wires": [{"source_id": "alpha", "target_id": "bravo", "pct": MARKUP}],
            "bot_centers": CENTRES,
        }
    )
    drawn = draw_sheet(browser, payload)
    label = only(drawn, "wire-sheet/wire/badge/badge-label")
    assert label["text"] == wcs.LABEL_FORMAT.format(pct=MARKUP)
    assert browser.js("window.HOST.querySelectorAll('img').length") == 0
    assert browser.parsed("window.VIOLATIONS") == []


def test_a_bot_name_carrying_markup_is_written_as_an_attribute_not_an_element(
    browser: Browser,
):
    browser.js(WATCH_VIOLATIONS)
    payload = bridge_payload(
        tab={
            "wires": [{"source_id": MARKUP, "target_id": "bravo", "pct": 10}],
            "bot_centers": dict(CENTRES, **{MARKUP: [40.0, 40.0]}),
        }
    )
    drawn = draw_sheet(browser, payload)
    group = only(drawn, "wire-sheet/wire")
    assert group["attrs"]["data-source"] == MARKUP
    assert browser.js("window.HOST.querySelectorAll('img').length") == 0
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_markup_check_counts_an_image_the_page_really_makes(browser: Browser):
    draw_sheet(browser, state_payload("wires"))
    browser.js("window.HOST.firstChild.appendChild(document.createElement('img'));")
    assert browser.js("window.HOST.querySelectorAll('img').length") == 1


def test_a_qt_label_reads_the_same_markup_as_an_image_and_not_as_characters(qapp):
    """Measures why no bot name is ever given to a QLabel."""
    assert qapp is not None
    core = pytest.importorskip("PySide6.QtCore")
    widgets = pytest.importorskip("PySide6.QtWidgets")
    as_markup = widgets.QLabel(MARKUP)
    as_characters = widgets.QLabel(MARKUP)
    as_characters.setTextFormat(core.Qt.TextFormat.PlainText)
    markup_width = as_markup.sizeHint().width()
    character_width = as_characters.sizeHint().width()
    assert markup_width < character_width, (
        f"a QLabel drew the markup {markup_width}px wide against "
        f"{character_width}px for the same text as characters"
    )


def test_the_shipped_sheet_gives_no_text_to_a_qt_label():
    body = SHIPPED_PATH.read_text(encoding="utf-8")
    assert "QLabel" not in body, "the shipped sheet grew a QLabel"
    assert "drawText" in body, "the shipped sheet no longer draws its own text"


LONG_NAME = "n" * 200

HOSTILE: dict = {
    "no_source_id": {"wires": [{"target_id": "bravo", "pct": 10}]},
    "no_target_id": {"wires": [{"source_id": "alpha", "pct": 10}]},
    "no_pct": {"wires": [{"source_id": "alpha", "target_id": "bravo"}]},
    "null_pct": {
        "wires": [{"source_id": "alpha", "target_id": "bravo", "pct": None}],
        "bot_centers": CENTRES,
    },
    "null_centre": {"wires": WIRES, "bot_centers": dict(CENTRES, alpha=None)},
    "number_where_a_name_belongs": {
        "wires": [{"source_id": 7, "target_id": 3, "pct": 10}],
        "bot_centers": {"7": [1.0, 2.0], "3": [3.0, 4.0]},
    },
    "text_where_a_number_belongs": {
        "wires": [{"source_id": "alpha", "target_id": "bravo", "pct": "40"}],
        "bot_centers": CENTRES,
    },
    "text_opacity": dict(WIRED_TAB, wire_opacity_pct="loud"),
    "nan_phase": {
        "wires": [
            {"source_id": "alpha", "target_id": "bravo", "pct": 10, "phase": math.nan}
        ],
        "bot_centers": CENTRES,
    },
    "inf_centre": {"wires": WIRES, "bot_centers": dict(CENTRES, alpha=[math.inf] * 2)},
    "minus_inf_centre": {
        "wires": WIRES,
        "bot_centers": dict(CENTRES, alpha=[-math.inf] * 2),
    },
    "enormous_pct": {
        "wires": [{"source_id": "alpha", "target_id": "bravo", "pct": 10**24}],
        "bot_centers": CENTRES,
    },
    "two_hundred_character_name": {
        "wires": [{"source_id": LONG_NAME, "target_id": "bravo", "pct": 10}],
        "bot_centers": dict(CENTRES, **{LONG_NAME: [40.0, 40.0]}),
    },
    "markup_name": {
        "wires": [{"source_id": MARKUP, "target_id": "bravo", "pct": 10}],
        "bot_centers": dict(CENTRES, **{MARKUP: [40.0, 40.0]}),
    },
    "newline_pct": {
        "wires": [{"source_id": "alpha", "target_id": "bravo", "pct": "a\nb"}],
        "bot_centers": CENTRES,
    },
    "duplicate_name": {
        "wires": [
            {"source_id": "alpha", "target_id": "bravo", "pct": 10},
            {"source_id": "alpha", "target_id": "bravo", "pct": 90},
        ],
        "bot_centers": CENTRES,
    },
    "a_wire_to_itself": {
        "wires": [{"source_id": "alpha", "target_id": "alpha", "pct": 10}],
        "bot_centers": CENTRES,
    },
    "a_wire_to_nowhere": {
        "wires": [{"source_id": "alpha", "target_id": "nobody", "pct": 10}],
        "bot_centers": CENTRES,
    },
}
HOSTILE_NAMES = tuple(sorted(HOSTILE))


def surface_outcome(name: str) -> dict:
    """What the surface answers for one hostile tab, or the refusal it raises."""
    try:
        payload = bridge_payload(tab=HOSTILE[name])
    except Exception as why:  # noqa: BLE001
        return {"refused": type(why).__name__, "detail": str(why)[:80]}
    return {
        "branches": payload["paint_branches"],
        "operations": len(payload["drawing_calls"]),
        "wire_order": payload["tab"]["wire_order"],
        "payload": payload,
    }


@pytest.mark.parametrize("name", HOSTILE_NAMES)
def test_the_surface_and_the_module_answer_the_same_for_a_hostile_payload(
    js: JsRuntime, name: str
):
    outcome = surface_outcome(name)
    if "refused" in outcome:
        assert outcome["refused"] in ("KeyError", "TypeError", "ValueError"), outcome
        assert outcome["detail"], name
        return
    try:
        js.push(outcome["payload"])
    except AssertionError as why:
        assert "SyntaxError" in str(why), str(why)[:160]
        return
    counts = js.ask("counts()")
    assert counts["operations"] == outcome["operations"]
    assert js.ask("wireNames()") == outcome["wire_order"]
    assert counts["drawn"] == outcome["branches"].count("wire.drawn")


@pytest.mark.parametrize("name", HOSTILE_NAMES)
def test_the_hostile_walk_reaches_a_leaf_of_every_hostile_payload(name: str):
    outcome = surface_outcome(name)
    if "refused" in outcome:
        assert outcome["detail"], name
        return
    kinds = python_kinds(outcome["payload"])
    assert kinds[".tab.wires"] == "object"
    leaves = {path for path, kind in kinds.items() if kind not in ("object",)}
    assert leaves, f"{name}: the walk reached no leaf, so it read nothing"


def test_the_hostile_walk_reads_a_scalar_standing_where_a_bag_belongs():
    kinds = python_kinds({"tab": {"wires": 4, "bot_centers": None}})
    assert kinds[".tab.wires"] == "number"
    assert kinds[".tab.bot_centers"] == "null"


@pytest.mark.parametrize("name", ("a_wire_to_itself", "a_wire_to_nowhere"))
def test_a_wire_with_no_second_bot_is_drawn_or_skipped_as_the_surface_says(
    js: JsRuntime, name: str
):
    outcome = surface_outcome(name)
    js.push(outcome["payload"])
    assert js.ask("counts()")["drawn"] == outcome["branches"].count("wire.drawn")
    assert js.ask("wireNames()") == outcome["wire_order"]


def test_two_wires_of_the_same_name_are_both_kept_in_the_published_order(js: JsRuntime):
    outcome = surface_outcome("duplicate_name")
    js.push(outcome["payload"])
    names = js.ask("wireNames()")
    assert len(names) == 2 and names[0] == names[1]
    assert js.named("wireAt", names[0])["at"] == 1


def test_a_two_hundred_character_name_stretches_no_drawn_box(browser: Browser):
    outcome = surface_outcome("two_hundred_character_name")
    drawn = draw_sheet(browser, outcome["payload"])
    group = only(drawn, "wire-sheet/wire")
    assert group["attrs"]["data-source"] == LONG_NAME
    badge = only(drawn, "wire-sheet/wire/badge")
    plate = calls_of(outcome["payload"], wcs.DRAW_ROUNDED_RECT)[0]
    assert badge["style"]["width"] == f"{js_number(plate[1][2])}px"


def test_the_shipped_sheet_has_no_layout_so_it_publishes_no_margin(qapp):
    """A bare overlay widget carries the contents margins this host gives it."""
    assert qapp is not None
    widgets = pytest.importorskip("PySide6.QtWidgets")
    bare = widgets.QWidget()
    margins = bare.contentsMargins()
    assert bare.layout() is None
    assert (
        margins.left(),
        margins.top(),
        margins.right(),
        margins.bottom(),
    ) == (0, 0, 0, 0)
    assert not bridge_payload(tab=WIRED_TAB).get("margins")


def test_the_renderer_page_loads_the_module_after_the_ones_it_asks():
    body = INDEX_HTML.read_text(encoding="utf-8")
    order = re.findall(r'src="\.\./\.\./src/gui/web/([a-z_]+)\.js"', body)
    assert "wire_canvas" in order, "the page never loads the wire module"
    for needed in ("header_strip", "bot_visualizer", "design_tokens", "shared_widgets"):
        assert order.index(needed) < order.index("wire_canvas"), needed
