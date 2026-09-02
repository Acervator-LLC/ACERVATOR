"""The React Fold Tranches token panel, against fold_tokens_surface.py."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import fold_tokens_surface as surface
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    new_engine,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "fold_tokens.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body writes into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

API = "acervatorFoldTokens."
SETTER = "acervatorSetFoldTokens"

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 3
HOST_WIDTH_PX = 900
HOST_HEIGHT_PX = 400

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

LONG_NAME = "z" * 200
MARKUP_NAME = "<img src='x'><b>bold</b>"
NEWLINE_NAME = "one\ntwo"

SWAPPED_ALPHA = "#123a63ff"
OTHER_COLOUR = "#00ffcc"

STATES: dict = {
    "bare": [],
    "one": [[surface.STEP_ARBITER, surface.ARBITER_PARENT]],
    "many": [
        [surface.STEP_FINITE, 1.5],
        [surface.STEP_ARBITER, surface.ARBITER_SIBLING],
        [surface.STEP_AGE, 3700],
        [surface.STEP_BORDER, surface.FOLD_TRANCHE_BG_HEX],
        [surface.STEP_RATIO, 10, 5, 0],
    ],
    "refused": [[surface.STEP_FINITE, 1.5], [surface.STEP_AGE, "not a number"]],
    "unknown": [["no_such_step"]],
}
STATE_NAMES = tuple(STATES)


def as_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True))


def state_payload(name: str) -> dict:
    return as_json(surface.view_model({"steps": STATES[name]}))


def token_payload() -> dict:
    return as_json(dss.view_model({}))


#: The merged pieces the page loads beside this module, needed at call time.
SHARED_MODULES = (WEB / "table_cells.js", WEB / "header_strip.js")


class JsRuntime(JsEngine):
    """A QJSEngine holding the module, with a setter and one raised answer."""

    module_path = MODULE_PATH
    setter = SETTER

    def __init__(self, engine: Any, source: str) -> None:
        super().__init__(engine, source)
        for path in SHARED_MODULES:
            loaded = engine.evaluate(path.read_text(encoding="utf-8"), path.name)
            assert not loaded.isError(), path.name + " -> " + loaded.toString()

    def called(self, method: str, value: Any) -> Any:
        self.bind_json("ARG", value)
        return self.json(API + method + "(JSON.parse(ARG))")


@pytest.fixture()
def js(qapp) -> JsRuntime:
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


def declared_fields(js: JsRuntime) -> list:
    return js.json(API + "declaredNames()")


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, state: str
):
    """A field with no answer is a value that stops at the bridge."""
    payload = state_payload(state)
    js.push(payload)
    named = declared_fields(js)
    missing = sorted(set(payload) - set(named))
    assert (
        not missing
    ), f"{len(missing)} published fields the module never names: {missing}"
    extra = sorted(set(named) - set(payload))
    assert not extra, f"the module names fields the surface has none of: {extra}"
    js.bind_json("NAMES", named)
    answered = js.json(
        "JSON.parse(NAMES).map(function (n) { return " + API + "field(n); })"
    )
    differing = {
        name: (payload[name], answered[at])
        for at, name in enumerate(named)
        if answered[at] != payload[name]
    }
    assert not differing, (
        f"{state}: {len(differing)} of {len(payload)} published fields differ: "
        f"{sorted(differing)}"
    )


def test_the_whole_payload_check_names_a_field_only_the_surface_holds(js: JsRuntime):
    payload = state_payload("many")
    payload["only_on_the_surface"] = []
    js.push(payload)
    assert sorted(set(payload) - set(declared_fields(js))) == ["only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_answers_for(
    js: JsRuntime,
):
    payload = state_payload("many")
    assert payload.pop("ran") is not None
    js.push(payload)
    assert sorted(set(declared_fields(js)) - set(payload)) == ["ran"]


def test_the_whole_payload_check_names_one_changed_value(js: JsRuntime):
    payload = state_payload("many")
    payload["ran"] += 1
    js.push(payload)
    original = state_payload("many")
    differing = sorted(
        name for name in original if js.called("field", name) != original[name]
    )
    assert differing == ["ran"], f"the check named {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    report = js.push(payload)
    assert report["declared"]["fields"] == len(payload)
    assert report["held"]["fields"] == len(payload)
    assert report["declared"]["steps"] == len(payload["tokens"]["STEP_NAMES"])
    assert report["held"]["steps"] == len(payload["step_names"])
    assert report["declared"]["ran"] == payload["ran"]
    assert report["held"]["ran"] == len(payload["calls"])
    assert report["declared"]["colours"] == report["held"]["colours"]


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    payload = state_payload("many")
    declared = len(payload)
    del payload["bus_emits"]
    report = js.push(payload)
    assert report["declared"]["fields"] == declared
    assert report["held"]["fields"] == declared - 1
    assert [one["field"] for one in report["faults"]] == ["bus_emits"]


def test_a_dropped_call_shortens_the_held_step_count(js: JsRuntime):
    payload = state_payload("many")
    payload["calls"].pop()
    report = js.push(payload)
    assert report["declared"]["ran"] == len(STATES["many"])
    assert report["held"]["ran"] == len(STATES["many"]) - 1


def python_kinds(payload: dict) -> dict:
    found: dict = {}

    def descend(path: str, value: Any) -> None:
        if isinstance(value, dict):
            walk(path, value)
            return
        if isinstance(value, list):
            for at, one in enumerate(value):
                inner = f"{path}.{at}"
                found[inner] = JS_TYPE_OF[type(one).__name__]
                descend(inner, one)

    def walk(prefix: str, node: dict) -> None:
        for name, value in node.items():
            path = f"{prefix}.{name}" if prefix else name
            found[path] = JS_TYPE_OF[type(value).__name__]
            descend(path, value)

    walk("", payload)
    return found


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_value_of_every_state_arrives_as_the_type_it_left_as(
    js: JsRuntime, state: str
):
    """A payload value that changes kind in transit reads right and paints wrong."""
    payload = state_payload(state)
    js.push(payload)
    expected = python_kinds(payload)
    actual = js.json(API + "kinds()")
    differing = {
        path: (kind, actual.get(path))
        for path, kind in expected.items()
        if actual.get(path) != kind
    }
    assert not differing, (
        f"{state}: {len(differing)} of {len(expected)} values changed type: "
        f"{sorted(differing)}"
    )
    assert sorted(actual) == sorted(expected)


def test_the_type_check_names_one_value_that_changed_shape(js: JsRuntime):
    payload = state_payload("many")
    payload["ran"] = str(payload["ran"])
    js.push(payload)
    expected = python_kinds(state_payload("many"))
    actual = js.json(API + "kinds()")
    assert sorted(p for p, k in expected.items() if actual.get(p) != k) == ["ran"]


def test_the_type_walk_names_a_scalar_where_a_call_belongs(js: JsRuntime):
    """A scalar where the payload lists a call must not read as that call."""
    payload = state_payload("many")
    payload["calls"][1] = 7
    js.push(payload)
    actual = js.json(API + "kinds()")
    assert actual.get("calls.1") == "number"
    assert "calls.1.0" not in actual


def test_the_type_walk_names_a_null_where_a_step_name_belongs(js: JsRuntime):
    payload = state_payload("many")
    payload["calls"][1][0] = None
    js.push(payload)
    assert js.json(API + "kinds()").get("calls.1.0") == "null"


PLAIN_TYPES = (str, int, float, bool, type(None))


def not_plain_data(payload: Any) -> list:
    """Every dotted path in payload whose value is not plain data."""
    found: list = []

    def walk(path: str, value: Any) -> None:
        if isinstance(value, dict):
            for name, inner in value.items():
                walk(f"{path}.{name}" if path else str(name), inner)
            return
        if isinstance(value, (list, tuple)):
            for at, inner in enumerate(value):
                walk(f"{path}.{at}", inner)
            return
        if not isinstance(value, PLAIN_TYPES):
            found.append(path)

    walk("", payload)
    return found


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_surface_publishes_no_live_object(state: str):
    """A live object on the payload is a value the renderer cannot serialise."""
    raw = surface.build_view_model(surface.FoldTokensModel(), STATES[state])
    assert not_plain_data(raw) == [], f"{state} publishes {not_plain_data(raw)}"


def test_the_plain_data_walk_names_a_live_object_put_on_the_payload():
    raw = surface.build_view_model(surface.FoldTokensModel(), [])
    raw["calls"] = [[surface.STEP_FINITE, surface.FoldTokensModel()]]
    assert not_plain_data(raw) == ["calls.0.1"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reads_no_value_that_is_not_plain_data(js: JsRuntime, state: str):
    js.push(state_payload(state))
    assert js.json(API + "notPlainData()") == []


def test_the_plain_data_check_names_a_function_bound_into_the_payload(js: JsRuntime):
    js.push(state_payload("one"))
    js.run("acervatorFoldTokens.payload();")
    js.run(SETTER + "(Object.assign(" + API + "payload(), { ran: function () {} }));")
    assert js.json(API + "notPlainData()") == [{"path": "ran", "kind": "function"}]


def shown_values() -> set:
    """Every string the panel paints or shows as a tooltip, from every state."""
    found: set = set()
    for name in STATE_NAMES:
        payload = state_payload(name)
        tokens = payload["tokens"]
        found |= set(tokens["TRANCHE_ROW_BORDER_BY_BG"])
        found |= set(tokens["TRANCHE_ROW_BORDER_BY_BG"].values())
        found |= set(tokens["FOLD_SORT_ORDERS"])
        found |= set(tokens["FOLD_COLUMN_TOOLTIPS"])
        found |= set(tokens["ARBITER_LABELS"].values())
        found |= set(tokens["FOLD_SOURCE_TOOLTIPS"])
        found |= set(tokens["FOLD_SOURCE_TOOLTIPS"].values())
    return {one for one in found if one}


def published_strings() -> set:
    found: set = set()

    def walk(node: Any) -> None:
        if isinstance(node, str):
            found.add(node)
        elif isinstance(node, dict):
            for key, value in node.items():
                found.add(str(key))
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for name in STATE_NAMES:
        walk(state_payload(name))
    return {one for one in found if one}


def token_values() -> set:
    found: set = set()
    for value in token_payload().values():
        if isinstance(value, str):
            found.add(value)
        elif isinstance(value, dict):
            found |= {one for one in value.values() if isinstance(one, str)}
    return {one for one in found if one}


SHOWN_VALUES = shown_values()
PUBLISHED_STRINGS = published_strings()
TOKEN_VALUES = token_values()
MODULE_LITERALS = js_literals(MODULE_SOURCE)

#: NAMED_WORDS lists every published string the module may write.
NAMED_WORDS = sorted(
    set(state_payload("bare"))
    | set(state_payload("bare")["tokens"])
    | set(state_payload("refused")["refused"])
    | {surface.METHOD}
)


def test_the_module_writes_no_number():
    """A numeric literal typed here is a second source for a value the surface owns."""
    assert not MODULE_LITERALS["numbers"], (
        "fold_tokens.js holds numeric literals: " f"{MODULE_LITERALS['numbers']}"
    )


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"fold_tokens.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_panel_shows():
    written = sorted(set(MODULE_LITERALS["strings"]) & SHOWN_VALUES)
    assert not written, f"fold_tokens.js spells out panel values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"fold_tokens.js spells out token values: {written}"


def test_the_module_names_only_the_surface_words_it_must_read():
    written = sorted(set(MODULE_LITERALS["strings"]) & PUBLISHED_STRINGS)
    assert set(written) <= set(NAMED_WORDS), (
        "the module names published strings the list does not allow: "
        f"{sorted(set(written) - set(NAMED_WORDS))}"
    )


def test_every_named_word_is_a_name_and_not_a_value_the_panel_shows():
    overlap = sorted(set(NAMED_WORDS) & SHOWN_VALUES)
    assert not overlap, f"these named words are values the panel shows: {overlap}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        "fold_tokens.js holds a slash outside a comment, which the literal scan "
        f"cannot read: {MODULE_LITERALS['slashes']}"
    )


WRITTEN_LINES: dict = {
    "colour": 'var written = "#00ffcc";',
    "fill": 'var written = "' + surface.FOLD_TRANCHE_BG_HEX + '";',
    "border": 'var written = "' + surface.FOLD_TRANCHE_BORDER_HEX + '";',
    "order": 'var written = "' + surface.FOLD_SORT_QUEUE_ORDER + '";',
    "arbiter_word": 'var written = "' + surface.ARBITER_LABELS["parent"] + '";',
    "source_word": 'var written = "' + surface.FOLD_SOURCE_MANUAL_SCRUM + '";',
    "column_tip": 'var written = "' + surface.FOLD_COLUMN_TOOLTIPS[0] + '";',
    "row_height": "var written = " + str(surface.TRANCHE_ROW_HEIGHT_PX) + ";",
    "border_width": "var written = " + str(surface.TRANCHE_ROW_BORDER_PX) + ";",
    "number": "var written = 12;",
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
    if strings & SHOWN_VALUES:
        caught.add("shown_value")
    if strings & TOKEN_VALUES:
        caught.add("token_value")
    if found["slashes"]:
        caught.add("regex")
    return caught


@pytest.mark.parametrize("kind", sorted(WRITTEN_LINES))
def test_the_literal_scan_names_one_written_line(kind: str):
    assert caught_by_scan(WRITTEN_LINES[kind]), f"the scan reported nothing on {kind}"


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    found = js_literals('// #00ffcc\nvar kept = "kept";')
    assert found["strings"] == ["kept"]
    assert not found["numbers"]


def test_each_written_literal_is_caught_in_the_module_file_itself():
    """The original is read inside the swap so no other worker's copy is written."""
    original = MODULE_PATH.read_bytes()
    before = hashlib.sha256(original).hexdigest()
    assert original.decode("utf-8") == MODULE_SOURCE
    caught_each = {}
    try:
        for kind in sorted(WRITTEN_LINES):
            swap_module(MODULE_PATH, original + WRITTEN_LINES[kind].encode("utf-8"))
            caught_each[kind] = caught_by_scan(MODULE_PATH.read_text(encoding="utf-8"))
            swap_module(MODULE_PATH, original)
            after = hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()
            assert after == before, f"the file was not restored after the {kind} line"
    finally:
        swap_module(MODULE_PATH, original)
    quiet = sorted(kind for kind, caught in caught_each.items() if not caught)
    assert not quiet, f"the scan reported nothing on these lines in the file: {quiet}"
    assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before


def test_the_written_file_is_still_a_module_the_page_can_run(js: JsRuntime):
    for kind, line in sorted(WRITTEN_LINES.items()):
        runtime = JsRuntime(js.engine_of(), MODULE_SOURCE + line)
        assert runtime.json("typeof " + SETTER) == "function", kind


def test_every_colour_the_panel_carries_is_swept_for_the_alpha_order_fault(
    js: JsRuntime,
):
    """Every published colour is swept for the eight-digit shape Qt reads first."""
    js.push(state_payload("many"))
    swept = js.json(API + "colourTokens()")
    assert len(swept) >= len(surface.TRANCHE_ROW_BORDER_BY_BG) * 2
    assert [one for one in swept if len(str(one["value"])) != len("#aabbcc")] == []
    assert js.json(API + "faults()") == []


def test_the_alpha_sweep_names_a_colour_written_with_eight_digits(js: JsRuntime):
    payload = state_payload("many")
    payload["tokens"]["FOLD_TRANCHE_BG_HEX"] = SWAPPED_ALPHA
    report = js.push(payload)
    assert [one["fault"] for one in report["faults"]] == ["swapped-alpha"]
    assert report["faults"][0]["detail"] == SWAPPED_ALPHA


@pytest.mark.parametrize("state", STATE_NAMES)
def test_no_bag_the_surface_publishes_carries_a_key_a_browser_would_move(
    js: JsRuntime, state: str
):
    """A digit key is listed before every worded key, which loses the written order."""
    js.push(state_payload(state))
    assert [
        one for one in js.json(API + "faults()") if one["fault"] == "reordered-key"
    ] == []


def test_the_bag_order_check_names_a_digit_key_put_into_a_published_bag(js: JsRuntime):
    payload = state_payload("many")
    payload["timers"]["0"] = 1
    report = js.push(payload)
    moved = [one for one in report["faults"] if one["fault"] == "reordered-key"]
    assert [one["detail"] for one in moved] == ["0"]


def test_the_offered_orders_are_published_as_a_list_and_read_in_that_order(
    js: JsRuntime,
):
    js.push(state_payload("many"))
    assert js.json(API + "orders()") == list(surface.FOLD_SORT_ORDERS)


def test_each_fill_resolves_its_own_border_by_name_and_not_by_position(js: JsRuntime):
    js.push(state_payload("many"))
    named = js.json(API + "fillNames()")
    assert named == list(surface.TRANCHE_ROW_BORDER_BY_BG)
    for fill in named:
        assert js.called("borderFor", fill) == surface.TRANCHE_ROW_BORDER_BY_BG[fill]


def test_the_border_lookup_answers_for_no_fill_the_map_does_not_know(js: JsRuntime):
    js.push(state_payload("many"))
    assert js.called("borderFor", SWAPPED_ALPHA) is None


def test_each_driven_step_is_read_back_by_its_own_name(js: JsRuntime):
    js.push(state_payload("many"))
    answered = js.json(API + "answers()")
    assert sorted(answered) == sorted(step[0] for step in STATES["many"])
    assert answered[surface.STEP_BORDER] == surface.FOLD_TRANCHE_BORDER_HEX


def test_the_step_check_names_a_call_the_payload_never_declared(js: JsRuntime):
    payload = state_payload("many")
    payload["calls"][0][0] = "no_such_step"
    report = js.push(payload)
    assert [one["fault"] for one in report["faults"]] == ["unknown-step"]


@pytest.mark.parametrize("state", ["refused", "unknown"])
def test_a_refused_step_is_named_with_its_index_and_its_refusal(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    refused = js.json(API + "refusal()")
    assert refused is not None, f"{state} recorded no refusal"
    assert refused["step"] == payload["refused"]["step"]
    assert refused["index"] == payload["refused"]["index"]


def test_the_refusal_check_names_a_refusal_missing_its_own_step(js: JsRuntime):
    payload = state_payload("refused")
    del payload["refused"]["step"]
    report = js.push(payload)
    assert [one["detail"] for one in report["faults"]] == ["step"]


HOSTILE_FIELDS: dict = {
    "tokens missing": ("tokens", None),
    "tokens is a list": ("tokens", []),
    "step_names is text": ("step_names", "finite_number"),
    "step_names is null": ("step_names", None),
    "calls is a bag": ("calls", {}),
    "ran is text": ("ran", "1"),
    "ran disagrees": ("ran", 99),
    "ran is huge": ("ran", 10**24),
    "refused is a number": ("refused", 7),
    "method is a number": ("method", 7),
    "timers is a list": ("timers", []),
    "actions is null": ("actions", None),
}


@pytest.mark.parametrize("case", sorted(HOSTILE_FIELDS))
def test_a_hostile_field_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    """A payload the surface would never send must report, never raise."""
    name, value = HOSTILE_FIELDS[case]
    payload = state_payload("many")
    payload[name] = value
    report = js.push(payload)
    assert isinstance(report["faults"], list), case
    assert js.json(API + "isLoaded()") is True, case
    assert isinstance(js.json(API + "kinds()"), dict), case


HOSTILE_TOKENS: dict = {
    "fill map is text": ("TRANCHE_ROW_BORDER_BY_BG", "#123a63"),
    "fill map is null": ("TRANCHE_ROW_BORDER_BY_BG", None),
    "orders is a bag": ("FOLD_SORT_ORDERS", {}),
    "orders hold a number": ("FOLD_SORT_ORDERS", [1, 2]),
    "column tips is null": ("FOLD_COLUMN_TOOLTIPS", None),
    "arbiter labels is a list": ("ARBITER_LABELS", []),
    "row height is text": ("TRANCHE_ROW_HEIGHT_PX", "30"),
    "row height is nan": ("TRANCHE_ROW_HEIGHT_PX", "nan"),
    "row height is inf": ("TRANCHE_ROW_HEIGHT_PX", "inf"),
    "row height is minus inf": ("TRANCHE_ROW_HEIGHT_PX", "-inf"),
    "row height is huge": ("TRANCHE_ROW_HEIGHT_PX", 10**24),
    "a long name": ("FOLD_SORT_QUEUE_ORDER", LONG_NAME),
    "markup": ("FOLD_SORT_QUEUE_ORDER", MARKUP_NAME),
    "a newline": ("FOLD_SORT_QUEUE_ORDER", NEWLINE_NAME),
    "a duplicate order": ("FOLD_SORT_ORDERS", [surface.FOLD_SORT_QUEUE_ORDER] * 2),
    "no orders at all": ("FOLD_SORT_ORDERS", []),
}


@pytest.mark.parametrize("case", sorted(HOSTILE_TOKENS))
def test_a_hostile_token_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    name, value = HOSTILE_TOKENS[case]
    payload = state_payload("many")
    payload["tokens"][name] = value
    report = js.push(payload)
    assert isinstance(report["faults"], list), case
    assert isinstance(js.json(API + "orders()"), list), case
    assert isinstance(js.json(API + "fillNames()"), list), case
    assert isinstance(js.json(API + "colourTokens()"), list), case


def test_the_hostile_sweep_would_have_seen_a_module_that_stopped_answering(
    js: JsRuntime,
):
    """A module that raised on one hostile value would answer nothing at all."""
    payload = state_payload("many")
    payload["tokens"] = None
    js.push(payload)
    assert js.json(API + "orders()") == []
    assert js.json(API + "colourTokens()") == []


class Browser:
    """A Browser drives the real renderer page in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        for _ in range(PAGE_ATTEMPTS):
            self.open_page()
            if self.module_ready():
                return
        raise AssertionError(
            "the page never defined the fold token module in "
            + str(PAGE_ATTEMPTS)
            + " loads: readyState "
            + str(self.js("document.readyState"))
        )

    def open_page(self) -> None:
        from PySide6.QtCore import QEventLoop, QTimer, QUrl

        loop = QEventLoop()
        box: dict = {}

        def _loaded(ok: bool) -> None:
            box.setdefault("ok", ok)
            loop.quit()

        link = self._view.loadFinished.connect(_loaded)
        self._view.load(QUrl.fromLocalFile(str(INDEX_HTML)))
        QTimer.singleShot(JS_TIMEOUT_MS, loop.quit)
        loop.exec()
        self._view.loadFinished.disconnect(link)
        assert box.get("ok") is True, f"{INDEX_HTML.name} did not load: {box}"

    def module_ready(self) -> bool:
        for _ in range(READY_ROUNDS):
            if self.js("typeof window." + SETTER) == "function":
                return True
            self.settle(READY_STEP_MS)
        return False

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


STYLE_NAMES = ["backgroundColor", "borderTopColor", "borderTopWidth", "height"]

PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = '" + str(HOST_WIDTH_PX) + "px';"
    "window.HOST.style.height = '" + str(HOST_HEIGHT_PX) + "px';"
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
    "      found.push({ path: here, tag: el.tagName, attrs: attrs,"
    "        text: el.textContent, html: el.innerHTML,"
    "        width: el.getBoundingClientRect().width,"
    "        style: window.readStyle(el, names) });"
    "    }"
    "    Array.prototype.slice.call(el.children).forEach(function (child) {"
    "      walk(child, here); });"
    "  };"
    "  if (window.HOST.firstChild) { walk(window.HOST.firstChild, ''); }"
    "  return JSON.stringify(found); })()"
)

COUNT_ELEMENTS = (
    "[window.HOST.querySelectorAll('*').length,"
    " window.HOST.querySelectorAll('[data-part]').length]"
)


def draw_panel(browser: Browser, payload: dict) -> list:
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    browser.js(
        "acervatorSetTokens(JSON.parse(window.TOKENS));"
        "acervatorTokens.apply(document.documentElement);"
    )
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        SETTER + "(JSON.parse(window.PAYLOAD));" + API + "renderPanel(window.HOST);"
    )
    return json.loads(browser.js(READ_PARTS))


def at_path(parts: list, path: str) -> list:
    return [one for one in parts if one["path"] == path]


def test_every_child_the_page_draws_carries_its_own_name(browser: Browser):
    """A child with no name is a child no check can read."""
    draw_panel(browser, state_payload("many"))
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named, f"{every - named} drawn children carry no data-part"
    assert named > 0


def test_the_named_child_check_would_see_one_unnamed_child(browser: Browser):
    draw_panel(browser, state_payload("many"))
    browser.js("window.HOST.firstChild.appendChild(document.createElement('span'));")
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named + 1


def test_each_fill_swatch_paints_the_colour_and_border_the_surface_carries(
    browser: Browser,
):
    """The applied value is read against a probe built from the whole declaration."""
    payload = state_payload("many")
    parts = draw_panel(browser, payload)
    swatches = at_path(parts, "fold-tokens/token-fill")
    assert len(swatches) == len(surface.TRANCHE_ROW_BORDER_BY_BG)
    for one in swatches:
        fill = one["attrs"]["data-fill"]
        border = surface.TRANCHE_ROW_BORDER_BY_BG[fill]
        assert one["attrs"]["data-border"] == border
        written = browser.parsed(API + "colour(" + json.dumps(fill) + ")")
        edge = browser.parsed(API + "colour(" + json.dumps(border) + ")")
        probe = browser.parsed(
            "window.probeStyle("
            + json.dumps(
                "background: "
                + written
                + "; border-style: solid; border-width: "
                + str(surface.TRANCHE_ROW_BORDER_PX)
                + "px; border-color: "
                + edge
                + "; height: "
                + str(surface.TRANCHE_ROW_HEIGHT_PX)
                + "px;"
            )
            + ", JSON.parse(window.STYLE_NAMES))"
        )
        assert one["style"] == probe, f"{fill} drew {one['style']} against {probe}"


def test_the_rendered_comparison_would_see_one_repainted_swatch(browser: Browser):
    payload = state_payload("many")
    parts = draw_panel(browser, payload)
    first = at_path(parts, "fold-tokens/token-fill")[0]
    probe = browser.parsed(
        "window.probeStyle("
        + json.dumps("background: " + OTHER_COLOUR + ";")
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert first["style"]["backgroundColor"] != probe["backgroundColor"]


def test_the_panel_draws_the_orders_in_the_order_the_surface_lists_them(
    browser: Browser,
):
    parts = draw_panel(browser, state_payload("many"))
    drawn = [
        one["attrs"]["data-order"] for one in at_path(parts, "fold-tokens/token-order")
    ]
    assert drawn == list(surface.FOLD_SORT_ORDERS)


def test_the_panel_refuses_markup_a_hostile_token_carries(browser: Browser):
    """React writes the tags as text, so no element reaches the document."""
    payload = state_payload("many")
    payload["tokens"]["FOLD_SORT_ORDERS"] = [MARKUP_NAME]
    parts = draw_panel(browser, payload)
    drawn = at_path(parts, "fold-tokens/token-order")
    assert drawn[0]["text"] == MARKUP_NAME
    assert "<img" not in drawn[0]["html"]
    assert browser.parsed("window.HOST.querySelectorAll('img').length") == 0


def test_the_markup_refusal_would_see_a_tag_the_page_did_run(browser: Browser):
    draw_panel(browser, state_payload("many"))
    browser.js("window.HOST.firstChild.insertAdjacentHTML('beforeend', '<img>');")
    assert browser.parsed("window.HOST.querySelectorAll('img').length") == 1


def test_a_two_hundred_character_order_stretches_the_panel_rather_than_clipping(
    browser: Browser,
):
    """A CSS box grows to fit where Qt would clip, so the width is reported."""
    payload = state_payload("many")
    payload["tokens"]["FOLD_SORT_ORDERS"] = [LONG_NAME]
    parts = draw_panel(browser, payload)
    drawn = at_path(parts, "fold-tokens/token-order")[0]
    short = state_payload("many")
    short["tokens"]["FOLD_SORT_ORDERS"] = [surface.FOLD_SORT_QUEUE_ORDER]
    narrow = at_path(draw_panel(browser, short), "fold-tokens/token-order")[0]
    assert drawn["width"] > narrow["width"]
