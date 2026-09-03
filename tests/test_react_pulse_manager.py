"""``pulse_manager.js`` against ``pulse_manager_surface.py``, run in QJSEngine
and drawn in QWebEngineView."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import pulse_manager_surface as surface
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    drain_events,
    js_literals,
    load_order,
    new_engine,
    runs_after,
    swap_module,
)

MODULE_PATH = REPO_ROOT / "src" / "gui" / "web" / "pulse_manager.js"
SHIPPED_SOURCE = REPO_ROOT / "src" / "gui" / "widgets" / "pulse_manager.py"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body can write into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

API = "acervatorPulseManager."
SETTER = "acervatorSetPulse"
LOADER = "acervatorLoadPulse"

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 2
HOST_WIDTH_PX = 900
HOST_HEIGHT_PX = 600

#: Python type -> the JavaScript type the same value has after the
#: bridge's ``json.dumps``.
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

LONG_NAME = "L" * 200
MARKUP_NAME = '<b onclick="x">bold &amp; "quoted"</b>'
NEWLINE_NAME = "line one\nline two"
UNICODE_NAME = "₿ éèê BTC 交易 \U0001f680"
OTHER_COLOUR = "#1E90FF"
SWAPPED_COLOUR = "#80FF8800"

STATES = {
    "bare": {},
    "one_target_one_run": {"targets": ["accent button"], "ticks": 1},
    "two_targets_two_runs": {"targets": ["accent button", "heading"], "ticks": 2},
    "no_target_many_runs": {"ticks": 20},
    "an_elapsed_time": {"targets": ["accent button"], "elapsed_ms": 500},
    "stopped": {"stop": True, "targets": ["accent button"], "ticks": 1},
    "a_long_name": {"targets": [LONG_NAME], "ticks": 1},
    "markup_in_a_name": {"targets": [MARKUP_NAME], "ticks": 1},
    "a_newline_in_a_name": {"targets": [NEWLINE_NAME], "ticks": 1},
    "a_unicode_name": {"targets": [UNICODE_NAME], "ticks": 1},
    "two_names_the_same": {"targets": ["twin", "twin"], "ticks": 1},
    "a_number_where_a_name_belongs": {"targets": [42], "ticks": 1},
    "nothing_where_a_name_belongs": {"targets": [None], "ticks": 1},
}
STATE_NAMES = sorted(STATES)

DRAWN_STATES = [
    "bare",
    "two_targets_two_runs",
    "stopped",
    "markup_in_a_name",
    "two_names_the_same",
]


def bridge_payload(**params: Any) -> dict:
    """One request answered by the surface, encoded the way the bridge encodes it."""
    return json.loads(json.dumps(surface.view_model(params), ensure_ascii=True))


def state_payload(name: str) -> dict:
    return bridge_payload(**STATES[name])


BARE = state_payload("bare")
DECLARED = sorted(BARE)


class JsRuntime(JsEngine):

    module_path = MODULE_PATH
    setter = SETTER

    def pushed(self, payload: Any, edit: str = "") -> Any:
        """Set one payload, with `edit` run over it first, and answer the report."""
        self.bind_json("PAYLOAD", payload)
        return self.json(
            "(function () { var p = JSON.parse(PAYLOAD); "
            + edit
            + " return "
            + SETTER
            + "(p); })()"
        )

    def faults(self) -> list:
        return self.json(API + "faults()")

    def fault_kinds(self) -> list:
        return sorted({one["fault"] for one in self.faults()})


@pytest.fixture()
def js(qapp) -> JsRuntime:
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


# ---------------------------------------------------------------------
# The whole payload, both directions, every state
# ---------------------------------------------------------------------


def test_the_module_declares_every_name_the_payload_carries(js: JsRuntime):
    """A name on one side and not the other is a value nothing draws."""
    js.push(BARE)
    assert sorted(js.json(API + "declaredNames()")) == DECLARED
    assert len(DECLARED) == 28, DECLARED


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_declared_name_is_held_for_every_state(js: JsRuntime, state: str):
    report = js.push(state_payload(state))
    assert report["declared"]["fields"] == report["held"]["fields"]
    assert report["held"]["fields"] == len(DECLARED)


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_report_counts_what_the_payload_carries(js: JsRuntime, state: str):
    payload = state_payload(state)
    report = js.push(payload)
    assert report["held"]["targets"] == len(payload["seen"])
    assert report["held"]["steps"] == len(payload["calls"])
    assert report["held"]["applied"] == len(payload["applied"])
    assert report["held"]["skipped"] == len(payload["skipped"])
    assert report["held"]["failed"] == len(payload["failed"])
    assert report["declared"]["steps"] == len(payload["call_names"])
    assert report["declared"]["targets"] == payload["registered"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_whole_payload_comes_back_as_it_went_in(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    assert js.json(API + "payload()") == payload


def python_kinds(payload: Any) -> dict:
    """Every dotted path in one payload against the JavaScript type it takes."""
    found: dict = {}

    def walk(prefix: str, node: Any) -> None:
        if isinstance(node, dict):
            pairs = node.items()
        elif isinstance(node, list):
            pairs = [(str(at), one) for at, one in enumerate(node)]
        else:
            return
        for name, value in pairs:
            path = f"{prefix}.{name}" if prefix else name
            found[path] = JS_TYPE_OF[type(value).__name__]
            walk(path, value)

    walk("", payload)
    return found


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_value_arrives_as_the_type_it_left_as(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    assert js.json(API + "kinds()") == python_kinds(payload)


def test_the_type_reading_tells_two_different_types_apart(js: JsRuntime):
    """A type reading that answers the same for every value proves nothing."""
    payload = state_payload("bare")
    js.pushed(payload, "p.registered = String(p.registered);")
    assert js.json(API + "kinds()")["registered"] == "string"
    js.push(payload)
    assert js.json(API + "kinds()")["registered"] == "number"


NOT_A_PAYLOAD: list = [None, [], "a payload", 3, True]


def test_a_payload_that_is_not_a_bag_is_refused(js: JsRuntime):
    for given in NOT_A_PAYLOAD:
        js.bind_json("PAYLOAD", given)
        report = js.json(SETTER + "(JSON.parse(PAYLOAD))")
        assert report["declared"] is None, given
        assert [one["fault"] for one in report["faults"]] == ["not-an-object"], given
    assert js.push(BARE)["faults"] == []


def test_a_value_that_is_not_plain_data_is_named(js: JsRuntime):
    js.push(BARE)
    js.run(
        "(function () { var p = " + API + "payload();"
        " p.seen = [function () {}]; " + SETTER + "(p); })()"
    )
    assert js.json(API + "notPlainData()") == [{"path": "seen.0", "kind": "function"}]
    js.push(BARE)
    assert js.json(API + "notPlainData()") == []


# ---------------------------------------------------------------------
# The cadence
# ---------------------------------------------------------------------


def test_the_cadence_the_module_reads_is_the_delay_the_timer_runs_at(js: JsRuntime):
    """A cadence read from prose rather than from the timer is a wrong cadence."""
    js.push(BARE)
    assert js.json(API + "cadence()") == surface.TIMER_INTERVAL_MS
    assert BARE["timer"]["interval_ms"] == surface.TIMER_INTERVAL_MS
    assert BARE["timers"][BARE["timer"]["name"]] == surface.TIMER_INTERVAL_MS
    assert BARE["timer_delays_ms"] == [surface.TIMER_INTERVAL_MS]


def test_the_delay_the_shipped_timer_runs_at_is_the_delay_published(qapp):
    """The published delay drifted from the delay the shipped timer starts with."""
    assert qapp is not None
    from src.gui.widgets.pulse_manager import PulseManager

    driver = PulseManager()
    driver._timer.stop()
    assert driver._timer.interval() == surface.TIMER_INTERVAL_MS
    assert surface.TIMER_INTERVAL_MS == 50


def test_the_stylesheet_time_is_not_the_cadence_and_nothing_applies_it(js: JsRuntime):
    """The sheet names a two second animation no Qt style engine ever runs."""
    js.push(BARE)
    assert BARE["style_sheet_applied"] is False
    assert "animation: pulse 2s ease-in-out infinite;" in BARE["css"]
    assert js.json(API + "cadence()") == 50
    assert js.json(API + "field('style_sheet_applied')") is False


@pytest.mark.parametrize("given", [0, -50])
def test_a_cadence_of_zero_or_less_is_read_as_no_cadence(js: JsRuntime, given: int):
    js.pushed(BARE, f"p.timer.interval_ms = {given};")
    assert js.json(API + "cadence()") is None
    assert "not-a-cadence" in js.fault_kinds()
    js.push(BARE)
    assert js.json(API + "cadence()") == 50
    assert "not-a-cadence" not in js.fault_kinds()


@pytest.mark.parametrize(
    "edit",
    [
        "p.timer.interval_ms = 'soon';",
        "p.timer.interval_ms = null;",
        "p.timer.interval_ms = NaN;",
        "p.timer.interval_ms = Infinity;",
        "p.timer.interval_ms = -Infinity;",
        "p.timer.interval_ms = [50];",
        "delete p.timer.interval_ms;",
    ],
)
def test_a_cadence_that_is_not_a_number_is_read_as_no_cadence(js: JsRuntime, edit: str):
    js.pushed(BARE, edit)
    assert js.json(API + "cadence()") is None
    assert "not-a-cadence" in js.fault_kinds()


def test_the_three_places_the_delay_is_published_must_agree(js: JsRuntime):
    js.pushed(BARE, "p.timers[p.timer.name] = 80;")
    assert "disagrees" in js.fault_kinds()
    js.pushed(BARE, "p.timer_delays_ms = [80];")
    assert "disagrees" in js.fault_kinds()
    js.pushed(BARE, "p.timer_delays_ms = [];")
    assert "disagrees" in js.fault_kinds()
    js.push(BARE)
    assert "disagrees" not in js.fault_kinds()


def test_every_name_the_timer_bag_carries_is_read(js: JsRuntime):
    js.push(BARE)
    assert js.json(API + "timerKeys()") == [
        "name",
        "interval_ms",
        "active",
        "starts",
        "stops",
    ]
    for key in js.json(API + "timerKeys()"):
        js.pushed(BARE, f"delete p.timer.{key};")
        assert [one["field"] for one in js.faults() if one["fault"] == "missing"] == [
            key
        ], key
    js.push(BARE)
    assert "missing" not in js.fault_kinds()


# ---------------------------------------------------------------------
# Two lists of different lengths, and a published count
# ---------------------------------------------------------------------


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_published_count_matches_the_targets_seen(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    assert payload["registered"] == len(payload["seen"])
    assert "disagrees" not in js.fault_kinds()


def test_a_count_that_disagrees_with_the_targets_it_names_is_reported(js: JsRuntime):
    payload = state_payload("two_targets_two_runs")
    js.pushed(payload, "p.registered = 5;")
    named = [one for one in js.faults() if one["fault"] == "disagrees"]
    assert [one["detail"] for one in named] == [[5, 2]], named
    js.push(payload)
    assert "disagrees" not in js.fault_kinds()


def test_the_two_opacity_lists_are_counted_before_either_is_paired(js: JsRuntime):
    """One list is longer than the other and pairing by position would hide it."""
    payload = state_payload("two_targets_two_runs")
    assert len(payload["applied"]) == 4
    assert [len(one["opacities"]) for one in payload["seen"]] == [2, 2]
    js.pushed(payload, "p.applied = p.applied.slice(1);")
    named = [one for one in js.faults() if one["fault"] == "disagrees"]
    assert [one["detail"] for one in named] == [[3, 4]], named
    js.push(payload)
    assert "disagrees" not in js.fault_kinds()


def test_the_index_lists_are_not_paired_with_the_targets_by_position(js: JsRuntime):
    """The skipped and failed lists count runs, not targets, so lengths differ."""
    payload = state_payload("two_targets_two_runs")
    js.push(payload)
    assert payload["skipped"] == []
    assert payload["failed"] == []
    assert js.json(API + "list('skipped')") == []
    assert js.json(API + "list('failed')") == []


# ---------------------------------------------------------------------
# The opacity band
# ---------------------------------------------------------------------


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_opacity_sits_inside_the_published_band(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    for value in payload["applied"]:
        assert payload["opacity_floor"] <= value <= payload["opacity_ceiling"]
    assert "out-of-band" not in js.fault_kinds()


@pytest.mark.parametrize("given", ["2", "-0.5", "NaN", "Infinity", "null"])
def test_an_opacity_outside_the_band_is_reported(js: JsRuntime, given: str):
    payload = state_payload("two_targets_two_runs")
    js.pushed(payload, f"p.applied[0] = {given};")
    assert "out-of-band" in js.fault_kinds(), given
    js.push(payload)
    assert "out-of-band" not in js.fault_kinds()


def test_an_opacity_a_target_kept_is_read_as_well_as_the_flat_list(js: JsRuntime):
    payload = state_payload("two_targets_two_runs")
    js.pushed(payload, "p.seen[1].opacities[0] = 2;")
    named = [one for one in js.faults() if one["fault"] == "out-of-band"]
    assert [one["where"] for one in named] == ["seen"], named
    js.push(payload)
    assert "out-of-band" not in js.fault_kinds()


# ---------------------------------------------------------------------
# Order and identity, by name
# ---------------------------------------------------------------------


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_targets_keep_the_order_they_were_registered_in(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    assert js.json(API + "seenNames()") == [one["target"] for one in payload["seen"]]


def test_a_target_is_found_by_its_name_and_not_by_where_it_sits(js: JsRuntime):
    payload = state_payload("two_targets_two_runs")
    js.push(payload)
    first = payload["seen"][0]["opacities"]
    second = payload["seen"][1]["opacities"]
    assert js.json(API + "opacitiesFor('accent button')") == first
    js.pushed(payload, "p.seen.reverse();")
    assert js.json(API + "opacitiesFor('accent button')") == first
    assert js.json(API + "opacitiesFor('heading')") == second
    assert js.json(API + "opacitiesFor('never registered')") == []


def test_two_targets_of_one_name_are_reported(js: JsRuntime):
    payload = state_payload("two_names_the_same")
    js.push(payload)
    named = [one for one in js.faults() if one["fault"] == "duplicate-name"]
    assert [one["detail"] for one in named] == ["twin"], named
    js.push(state_payload("two_targets_two_runs"))
    assert "duplicate-name" not in js.fault_kinds()


def test_the_call_names_keep_their_published_order(js: JsRuntime):
    js.push(BARE)
    assert js.json(API + "callNames()") == list(surface.CALL_NAMES)
    assert js.json(API + "steps()") == BARE["calls"]


def test_a_step_the_payload_never_declared_is_reported(js: JsRuntime):
    js.pushed(BARE, "p.calls.push('never_declared');")
    named = [one for one in js.faults() if one["fault"] == "unknown-step"]
    assert [one["detail"] for one in named] == ["never_declared"], named
    js.push(BARE)
    assert "unknown-step" not in js.fault_kinds()


BAG_FIELDS = ["actions", "timer", "timers"]


@pytest.mark.parametrize("name", BAG_FIELDS)
def test_no_bag_the_surface_publishes_carries_a_key_a_browser_would_move(
    js: JsRuntime, name: str
):
    js.push(BARE)
    assert js.json(API + f"bagKeys('{name}')") == list(BARE[name])
    for key in BARE[name]:
        assert js.json(API + f"isReorderedKey({json.dumps(key)})") is False


@pytest.mark.parametrize("name", BAG_FIELDS)
def test_the_moved_key_check_would_see_one(js: JsRuntime, name: str):
    js.pushed(BARE, f"p.{name}['12'] = p.{name}[Object.keys(p.{name})[0]];")
    named = [one for one in js.faults() if one["fault"] == "reordered-key"]
    assert [one["field"] for one in named] == ["12"], named


# ---------------------------------------------------------------------
# Every string this screen emits
# ---------------------------------------------------------------------


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


def shown_values() -> set:
    """Every string the panel draws as characters, from every state."""
    found: set = set()
    for name in STATE_NAMES:
        payload = state_payload(name)
        found.add(payload["css"])
        found |= {payload[key] for key in ("setter", "swallows")}
        found.add(payload["timer"]["name"])
        found |= set(payload["actions"]) | set(payload["actions"].values())
        found |= set(payload["timers"])
        found |= set(payload["call_names"]) | set(payload["calls"])
        found |= {
            one["target"] for one in payload["seen"] if isinstance(one["target"], str)
        }
    return {one for one in found if one}


PUBLISHED_STRINGS = published_strings()
SHOWN_VALUES = shown_values()
MODULE_LITERALS = js_literals(MODULE_SOURCE)

#: NAMED_WORDS lists every published string the module may write.
NAMED_WORDS = sorted(
    set(BARE) | set(BARE["timer"]) | {"target", "opacities"} | {surface.METHOD}
)


def test_every_string_the_screen_emits_is_one_the_surface_measured():
    """A word the panel shows that no measurement backs is a claim of its own."""
    measured = {
        BARE["css"],
        BARE["setter"],
        BARE["swallows"],
        BARE["method"],
        BARE["timer"]["name"],
    }
    measured |= set(BARE["actions"]) | set(BARE["actions"].values())
    measured |= set(BARE["timers"]) | set(BARE["call_names"])
    assert set(BARE["timers"]) == {BARE["timer"]["name"]}
    assert len(measured) == 16, sorted(measured)
    assert measured <= PUBLISHED_STRINGS
    assert BARE["setter"] == surface.OPACITY_SETTER
    assert BARE["swallows"] == surface.SWALLOWED_ERROR
    assert BARE["method"] == surface.METHOD


def test_the_module_writes_no_number():
    """A numeric literal typed here is a second source for a value the surface owns."""
    assert not MODULE_LITERALS["numbers"], (
        "pulse_manager.js holds numeric literals: " f"{MODULE_LITERALS['numbers']}"
    )


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"pulse_manager.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_panel_shows():
    written = sorted(set(MODULE_LITERALS["strings"]) & SHOWN_VALUES)
    assert not written, f"pulse_manager.js spells out panel values: {written}"


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
        "pulse_manager.js holds a slash outside a comment, which the "
        f"literal scan cannot read: {MODULE_LITERALS['slashes']}"
    )


WRITTEN_LINES: dict = {
    "colour": 'var written = "' + OTHER_COLOUR + '";',
    "swapped": 'var written = "' + SWAPPED_COLOUR + '";',
    "setter": 'var written = "' + surface.OPACITY_SETTER + '";',
    "swallows": 'var written = "' + surface.SWALLOWED_ERROR + '";',
    "timer_name": 'var written = "' + surface.TIMER_NAME + '";',
    "call_name": 'var written = "' + surface.CALL_NAMES[0] + '";',
    "action": 'var written = "' + list(surface.ACTIONS.values())[0] + '";',
    "delay": "var written = " + str(surface.TIMER_INTERVAL_MS) + ";",
    "phase_step": "var written = " + str(surface.PHASE_STEP) + ";",
    "opacity_mid": "var written = " + str(surface.OPACITY_MID) + ";",
    "run_cap": "var written = " + str(surface.RUN_CAP) + ";",
    "number": "var written = 12;",
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
    if found["slashes"]:
        caught.add("regex")
    return caught


@pytest.mark.parametrize("kind", sorted(WRITTEN_LINES))
def test_the_literal_scan_names_one_written_line(kind: str):
    assert caught_by_scan(WRITTEN_LINES[kind]), f"the scan reported nothing on {kind}"


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    found = js_literals("// " + OTHER_COLOUR + '\nvar kept = "kept";')
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
        if kind == "regex":
            continue
        runtime = JsRuntime(js.engine_of(), MODULE_SOURCE + line)
        assert runtime.json("typeof " + SETTER) == "function", kind


# ---------------------------------------------------------------------
# Colours, including a sub-block a declaration walk never enters
# ---------------------------------------------------------------------


def payload_strings(payload: Any) -> list:
    found: list = []

    def walk(node: Any) -> None:
        if isinstance(node, str):
            found.append(node)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return found


def test_the_payload_publishes_no_colour_at_all():
    """A colour would need a token, and this screen publishes none to check."""
    for name in STATE_NAMES:
        for one in payload_strings(state_payload(name)):
            assert not HEX_COLOUR.findall(one), (name, one)


def test_the_colour_sweep_reads_a_colour_in_a_hover_sub_block():
    """A sweep that never enters a sub-block reports zero on a sheet holding one."""
    sheet = "QPushButton { color: %s; } QPushButton:hover { color: %s; }" % (
        OTHER_COLOUR,
        SWAPPED_COLOUR,
    )
    assert HEX_COLOUR.findall(sheet) == [OTHER_COLOUR, SWAPPED_COLOUR]
    assert not HEX_COLOUR.findall(BARE["css"])


def test_the_swapped_alpha_check_reads_an_eight_digit_colour(js: JsRuntime):
    js.push(BARE)
    assert js.json(API + f"isSwappedAlpha({json.dumps(SWAPPED_COLOUR)})") is True
    assert js.json(API + f"isSwappedAlpha({json.dumps(OTHER_COLOUR)})") is False


def test_a_colour_written_alpha_first_anywhere_in_the_payload_is_reported(
    js: JsRuntime,
):
    js.pushed(BARE, f"p.setter = {json.dumps(SWAPPED_COLOUR)};")
    assert "swapped-alpha" in js.fault_kinds()
    js.push(BARE)
    assert "swapped-alpha" not in js.fault_kinds()


# ---------------------------------------------------------------------
# Hostile payloads
# ---------------------------------------------------------------------


@pytest.mark.parametrize("name", DECLARED)
def test_each_field_missing_is_reported(js: JsRuntime, name: str):
    js.pushed(BARE, f"delete p[{json.dumps(name)}];")
    named = [
        one for one in js.faults() if one["fault"] == "missing" and one["where"] is None
    ]
    assert [one["field"] for one in named] == [name], js.faults()


@pytest.mark.parametrize("name", DECLARED)
def test_each_field_set_to_nothing_is_reported(js: JsRuntime, name: str):
    js.pushed(BARE, f"p[{json.dumps(name)}] = null;")
    named = [one["field"] for one in js.faults() if one["fault"] == "null"]
    assert named == [name], js.faults()


#: The states whose own request carries the thing the reading names.
EXPECTED_FAULTS = {
    "markup_in_a_name": ["markup"],
    "two_names_the_same": ["duplicate-name"],
}


def test_no_field_of_a_whole_payload_is_reported(js: JsRuntime):
    """Every missing and null reading above needs a payload that reports neither."""
    for name in STATE_NAMES:
        js.push(state_payload(name))
        assert js.fault_kinds() == EXPECTED_FAULTS.get(name, []), (name, js.faults())


LIST_FIELDS = [
    "applied",
    "bus_topics",
    "call_names",
    "calls",
    "failed",
    "seen",
    "signals",
    "skipped",
    "timer_delays_ms",
    "widgets",
]

NUMBER_FIELDS = [
    "opacity_ceiling",
    "opacity_floor",
    "opacity_mid",
    "opacity_swing",
    "phase",
    "phase_start",
    "phase_step",
    "registered",
    "run_cap",
]

WORD_FIELDS = ["css", "method", "setter", "swallows"]
FLAG_FIELDS = ["paints", "style_sheet_applied"]


@pytest.mark.parametrize("name", LIST_FIELDS)
@pytest.mark.parametrize("given", ["3", "'a word'", "{}", "true"])
def test_a_scalar_or_a_bag_where_a_list_belongs_is_reported(
    js: JsRuntime, name: str, given: str
):
    """A scalar slipping past a list walk draws nothing and reports nothing."""
    js.pushed(BARE, f"p[{json.dumps(name)}] = {given};")
    named = [one["field"] for one in js.faults() if one["fault"] == "not-a-list"]
    assert named == [name], js.faults()


@pytest.mark.parametrize("name", BAG_FIELDS)
@pytest.mark.parametrize("given", ["3", "'a word'", "[]", "true"])
def test_a_scalar_or_a_list_where_a_bag_belongs_is_reported(
    js: JsRuntime, name: str, given: str
):
    js.pushed(BARE, f"p[{json.dumps(name)}] = {given};")
    named = [one["field"] for one in js.faults() if one["fault"] == "not-a-bag"]
    assert named == [name], js.faults()


@pytest.mark.parametrize("name", NUMBER_FIELDS)
@pytest.mark.parametrize("given", ["'50'", "true", "NaN", "Infinity", "-Infinity"])
def test_text_or_a_flag_where_a_number_belongs_is_reported(
    js: JsRuntime, name: str, given: str
):
    js.pushed(BARE, f"p[{json.dumps(name)}] = {given};")
    named = [one["field"] for one in js.faults() if one["fault"] == "not-a-number"]
    assert named == [name], js.faults()


@pytest.mark.parametrize("name", WORD_FIELDS)
def test_a_number_where_text_belongs_is_reported(js: JsRuntime, name: str):
    js.pushed(BARE, f"p[{json.dumps(name)}] = 12;")
    named = [one["field"] for one in js.faults() if one["fault"] == "not-a-word"]
    assert named == [name], js.faults()


@pytest.mark.parametrize("name", FLAG_FIELDS)
def test_a_word_where_a_flag_belongs_is_reported(js: JsRuntime, name: str):
    js.pushed(BARE, f"p[{json.dumps(name)}] = 'yes';")
    named = [one["field"] for one in js.faults() if one["fault"] == "not-a-flag"]
    assert named == [name], js.faults()


def test_a_number_no_run_could_ever_reach_is_read_as_the_number_it_is(js: JsRuntime):
    """A count of ten to the twenty-fourth is a real number and a wrong count."""
    js.pushed(BARE, "p.registered = 1e24;")
    named = [one for one in js.faults() if one["fault"] == "disagrees"]
    assert [one["detail"] for one in named] == [[1e24, 0]], named
    assert js.json(API + "field('registered')") == 1e24


def test_a_two_hundred_character_name_is_kept_whole(js: JsRuntime):
    payload = state_payload("a_long_name")
    js.push(payload)
    assert js.json(API + "seenNames()") == [LONG_NAME]
    assert len(js.json(API + "seenNames()")[0]) == 200


def test_a_newline_in_a_name_is_kept(js: JsRuntime):
    payload = state_payload("a_newline_in_a_name")
    js.push(payload)
    assert js.json(API + "seenNames()") == [NEWLINE_NAME]


def test_markup_in_a_name_is_reported_and_kept_as_the_characters_given(js: JsRuntime):
    payload = state_payload("markup_in_a_name")
    js.push(payload)
    named = [one for one in js.faults() if one["fault"] == "markup"]
    assert [one["detail"] for one in named] == [MARKUP_NAME], named
    assert js.json(API + "seenNames()") == [MARKUP_NAME]
    js.push(state_payload("one_target_one_run"))
    assert "markup" not in js.fault_kinds()


def test_a_name_that_is_a_number_or_nothing_is_drawn_and_not_refused(js: JsRuntime):
    js.push(state_payload("a_number_where_a_name_belongs"))
    assert js.json(API + "seenNames()") == [42]
    assert js.fault_kinds() == []
    js.push(state_payload("nothing_where_a_name_belongs"))
    assert js.json(API + "seenNames()") == [None]
    assert js.fault_kinds() == []


def test_a_target_row_that_is_a_scalar_does_not_slip_past_the_walk(js: JsRuntime):
    js.pushed(BARE, "p.seen = ['a name with no bag']; p.registered = 1;")
    assert js.json(API + "seenNames()") == ["a name with no bag"]
    assert js.json(API + "opacitiesFor('a name with no bag')") == []
    assert js.fault_kinds() == []


# ---------------------------------------------------------------------
# The request the surface refuses
# ---------------------------------------------------------------------


def test_a_request_asking_for_more_runs_than_the_cap_never_reaches_the_module():
    """A request the surface runs forever would freeze the one bridge process."""
    with pytest.raises(ValueError):
        surface.view_model({"ticks": 10**24})
    with pytest.raises(ValueError):
        surface.view_model({"elapsed_ms": 10**24})
    assert bridge_payload(ticks=surface.RUN_CAP)["run_cap"] == surface.RUN_CAP


def test_the_cap_the_payload_publishes_is_the_cap_the_surface_holds(js: JsRuntime):
    js.push(BARE)
    assert js.json(API + "field('run_cap')") == surface.RUN_CAP
    assert surface.RUN_CAP * surface.TIMER_INTERVAL_MS == 60_000


# ---------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------


def test_the_module_asks_the_method_the_bridge_registers(js: JsRuntime):
    from src.core import desktop_bridge

    assert js.json(API + "method") == surface.METHOD
    assert surface.METHOD in desktop_bridge.build_registry()


def test_the_module_reports_a_page_with_no_bridge(js: JsRuntime):
    js.run(LOADER + "();")
    drain_events()
    assert js.json(API + "loadError()") == "the preload bridge is not present"
    assert js.json(API + "isLoaded()") is False


def test_one_ask_is_answered_and_kept(js: JsRuntime):
    js.bind_json("PAYLOAD", BARE)
    js.run(
        "window.acervator = { asks: 0, call: function (m, p) {"
        "  this.asks += 1; return Promise.resolve(JSON.parse(PAYLOAD)); } };"
    )
    js.run(LOADER + "();" + LOADER + "();")
    drain_events()
    assert js.json("window.acervator.asks") == 1
    assert js.json(API + "isLoaded()") is True
    assert js.json(API + "payload()") == BARE


def test_a_refused_ask_is_reported_and_asked_again(js: JsRuntime):
    js.run(
        "window.acervator = { call: function () {"
        "  return Promise.reject(new Error('the backend refused')); } };"
    )
    js.run(LOADER + "();")
    drain_events()
    assert js.json(API + "loadError()") == "the backend refused"
    assert js.json(API + "isLoaded()") is False
    js.bind_json("PAYLOAD", BARE)
    js.run(
        "window.acervator = { call: function () {"
        "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
    )
    js.run(LOADER + "();")
    drain_events()
    assert js.json(API + "loadError()") is None
    assert js.json(API + "isLoaded()") is True


def test_forgetting_clears_everything_the_module_held(js: JsRuntime):
    js.push(BARE)
    assert js.json(API + "isLoaded()") is True
    js.run(API + "forget();")
    assert js.json(API + "isLoaded()") is False
    assert js.json(API + "payload()") == {}
    assert js.json(API + "faults()") == []
    assert js.json(API + "cadence()") is None


def test_the_renderer_loads_the_module():
    """A module the renderer never runs is one the window never reaches."""
    assert runs_after(load_order(), MODULE_PATH.name), load_order()


def test_the_order_reading_answers_no_for_a_module_it_never_runs():
    """The same reading of an order this module is absent from."""
    assert not runs_after(["boot.js"], MODULE_PATH.name)


# ---------------------------------------------------------------------
# What the shipped driver builds
# ---------------------------------------------------------------------


def test_this_screen_builds_no_widget_and_the_counter_can_report(qapp):
    """No caller name reaches a widget here, because the driver builds none."""
    assert qapp is not None
    assert surface.WIDGETS == ()
    assert surface.PAINTS is False
    from PySide6.QtWidgets import QLabel

    plain = QLabel(MARKUP_NAME)
    assert plain.sizeHint().width() > 0


def test_a_label_would_have_read_a_name_carrying_markup_as_markup(qapp):
    """A QLabel asks a narrower width for one name than a plain widget does."""
    assert qapp is not None
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel, QPushButton

    label = QLabel(MARKUP_NAME)
    as_markup = label.sizeHint().width()
    plain = QLabel(MARKUP_NAME)
    plain.setTextFormat(Qt.TextFormat.PlainText)
    as_characters = plain.sizeHint().width()
    assert as_markup < as_characters, (as_markup, as_characters)
    assert QPushButton(MARKUP_NAME).sizeHint().width() > as_markup
    assert label.text() == MARKUP_NAME


# ---------------------------------------------------------------------
# The page itself
# ---------------------------------------------------------------------


class Browser:
    """The real renderer page, loaded from disk in a Chromium view."""

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
                if self.js("typeof window." + SETTER) == "function":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the pulse module: readyState "
            + str(self.js("document.readyState"))
            + ", scripts "
            + str(self.js("document.scripts.length"))
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
    """The page, or a skip when Chromium is not installed with Qt."""
    assert qapp is not None
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    page = Browser()
    yield page
    page.close()


#: Every computed style property read off each drawn part.
STYLE_NAMES = ["opacity", "color", "backgroundColor", "fontSize", "whiteSpace"]

PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = '" + str(HOST_WIDTH_PX) + "px';"
    "window.HOST.style.height = '" + str(HOST_HEIGHT_PX) + "px';"
    "window.HOST.setAttribute('data-part', 'pulse-page');"
    "document.body.appendChild(window.HOST);"
    "window.readStyle = function (el, names) {"
    "  var computed = getComputedStyle(el);"
    "  var found = {};"
    "  names.forEach(function (n) { found[n] = computed[n]; });"
    "  return found; };"
    "window.probeStyle = function (cssText, names) {"
    "  var probe = document.createElement('span');"
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
    "      var own = '';"
    "      Array.prototype.slice.call(el.childNodes).forEach(function (n) {"
    "        if (n.nodeType === Node.TEXT_NODE) { own += n.nodeValue; } });"
    "      found.push({ path: here, tag: el.tagName, attrs: attrs,"
    "        text: own, whole: el.textContent, html: el.innerHTML,"
    "        children: el.children.length,"
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
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        SETTER + "(JSON.parse(window.PAYLOAD));" + API + "fill(window.HOST, null);"
    )
    return json.loads(browser.js(READ_PARTS))


def with_part(parts: list, name: str) -> list:
    return [one for one in parts if one["path"].split("/")[-1] == name]


def one_part(parts: list, name: str) -> dict:
    found = with_part(parts, name)
    assert len(found) == 1, f"{name} was drawn {len(found)} times"
    return found[0]


def test_the_panel_fills_the_named_space_the_window_left_for_it(browser: Browser):
    """A panel drawn outside the named space is a panel the window never shows."""
    parts = draw_panel(browser, BARE)
    assert browser.parsed(API + "spacePart") == "pulse-page"
    assert with_part(parts, "pulse-panel"), "the panel drew nothing into the space"


def test_every_child_the_page_draws_carries_its_own_name(browser: Browser):
    """A child with no name is a child no check can read."""
    draw_panel(browser, state_payload("two_targets_two_runs"))
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named, f"{every - named} drawn children carry no data-part"
    assert named > 0


def test_the_named_child_check_would_see_one_unnamed_child(browser: Browser):
    draw_panel(browser, state_payload("two_targets_two_runs"))
    browser.js("window.HOST.firstChild.appendChild(document.createElement('span'));")
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named + 1


#: Each declared name against the drawn part or attribute that reads it.
READ_BY = {
    "css": ("part", "sheet"),
    "style_sheet_applied": ("attr", ("sheet", "data-applied")),
    "timer": ("part", "timer-name"),
    "phase_start": ("part", "phase-start"),
    "phase": ("part", "phase-now"),
    "phase_step": ("part", "phase-step"),
    "opacity_mid": ("part", "opacity-mid"),
    "opacity_swing": ("part", "opacity-swing"),
    "opacity_floor": ("part", "opacity-floor"),
    "opacity_ceiling": ("part", "opacity-ceiling"),
    "setter": ("part", "driver-setter"),
    "swallows": ("part", "driver-swallows"),
    "run_cap": ("part", "driver-run-cap"),
    "registered": ("part", "driver-registered"),
    "applied": ("part", "applied-list"),
    "skipped": ("part", "skipped-list"),
    "failed": ("part", "failed-list"),
    "seen": ("part", "target-list"),
    "paints": ("part", "driver-paints"),
    "widgets": ("part", "widgets"),
    "signals": ("part", "signals"),
    "actions": ("part", "actions"),
    "timers": ("part", "timers"),
    "timer_delays_ms": ("part", "timer_delays_ms"),
    "bus_topics": ("part", "bus_topics"),
    "call_names": ("part", "call-list"),
    "calls": ("part", "step-list"),
    "method": ("attr", ("pulse-panel", "data-method")),
}


def test_every_value_the_surface_writes_is_read_back_by_the_panel(browser: Browser):
    """A value written and never read is a value the screen quietly drops."""
    assert sorted(READ_BY) == DECLARED
    parts = draw_panel(browser, state_payload("two_targets_two_runs"))
    for name, (kind, where) in sorted(READ_BY.items()):
        if kind == "part":
            assert with_part(parts, where), f"{name} reaches no drawn part"
        else:
            part, attr = where
            assert one_part(parts, part)["attrs"].get(attr) is not None, name


def test_the_read_back_check_would_see_a_value_no_part_draws(browser: Browser):
    parts = draw_panel(browser, BARE)
    assert not with_part(parts, "a-part-the-panel-never-draws")


@pytest.mark.parametrize("state", DRAWN_STATES)
def test_each_published_scalar_is_drawn_as_the_characters_it_carries(
    browser: Browser, state: str
):
    payload = state_payload(state)
    parts = draw_panel(browser, payload)
    assert one_part(parts, "timer-name")["text"] == payload["timer"]["name"]
    assert one_part(parts, "timer-delay")["text"] == str(
        payload["timer"]["interval_ms"]
    )
    assert one_part(parts, "driver-setter")["text"] == payload["setter"]
    assert one_part(parts, "driver-swallows")["text"] == payload["swallows"]
    assert one_part(parts, "driver-run-cap")["text"] == str(payload["run_cap"])
    assert one_part(parts, "driver-registered")["text"] == str(payload["registered"])
    assert one_part(parts, "driver-paints")["text"] == str(payload["paints"]).lower()


@pytest.mark.parametrize("state", DRAWN_STATES)
def test_the_drawn_cadence_is_the_delay_and_never_the_stylesheet_time(
    browser: Browser, state: str
):
    payload = state_payload(state)
    parts = draw_panel(browser, payload)
    assert one_part(parts, "timer-delay")["text"] == str(surface.TIMER_INTERVAL_MS)
    sheet = one_part(parts, "sheet")
    assert sheet["attrs"]["data-applied"] == "false"
    assert "2s" in sheet["text"]
    assert one_part(parts, "timer-delay")["text"] not in ("2s", "2000")


@pytest.mark.parametrize("state", DRAWN_STATES)
def test_each_target_row_is_found_by_its_own_name(browser: Browser, state: str):
    payload = state_payload(state)
    parts = draw_panel(browser, payload)
    rows = with_part(parts, "target-row")
    assert len(rows) == len(payload["seen"])
    assert [one["attrs"]["data-name"] for one in rows] == [
        str(one["target"]) for one in payload["seen"]
    ]
    assert [one["attrs"]["data-count"] for one in rows] == [
        str(len(one["opacities"])) for one in payload["seen"]
    ]


def test_a_row_is_read_by_its_name_and_not_by_where_it_sits(browser: Browser):
    payload = state_payload("two_targets_two_runs")
    reversed_payload = json.loads(json.dumps(payload))
    reversed_payload["seen"].reverse()
    parts = draw_panel(browser, reversed_payload)
    rows = with_part(parts, "target-row")
    by_name = {one["attrs"]["data-name"]: one for one in rows}
    assert sorted(by_name) == ["accent button", "heading"]
    assert by_name["accent button"]["attrs"]["data-index"] == "1"


def test_a_name_carrying_markup_is_drawn_as_characters(browser: Browser):
    """A name drawn as markup would lose the characters the caller gave."""
    parts = draw_panel(browser, state_payload("markup_in_a_name"))
    drawn = one_part(parts, "target-name")
    assert drawn["text"] == MARKUP_NAME
    assert drawn["children"] == 0
    assert "<b" not in drawn["html"]


def test_a_long_name_and_a_newline_reach_the_page_whole(browser: Browser):
    parts = draw_panel(browser, state_payload("a_long_name"))
    assert one_part(parts, "target-name")["text"] == LONG_NAME
    parts = draw_panel(browser, state_payload("a_newline_in_a_name"))
    assert one_part(parts, "target-name")["text"] == NEWLINE_NAME


@pytest.mark.parametrize("state", ["one_target_one_run", "two_targets_two_runs"])
def test_the_drawn_opacity_matches_a_probe_built_from_the_whole_declaration(
    browser: Browser, state: str
):
    """A probe built from a typed number would answer for a value nothing drew."""
    payload = state_payload(state)
    parts = draw_panel(browser, payload)
    drawn = with_part(parts, "target-opacity")
    assert len(drawn) == sum(len(one["opacities"]) for one in payload["seen"])
    for cell in drawn:
        declaration = "opacity: " + cell["text"] + ";"
        probe = browser.parsed(
            "window.probeStyle("
            + json.dumps(declaration)
            + ", JSON.parse(window.STYLE_NAMES))"
        )
        assert cell["style"]["opacity"] == probe["opacity"], (declaration, cell)


def test_the_opacity_probe_would_see_a_different_value(browser: Browser):
    draw_panel(browser, state_payload("one_target_one_run"))
    first = browser.parsed(
        "window.probeStyle('opacity: 0.5;', JSON.parse(window.STYLE_NAMES))"
    )
    second = browser.parsed(
        "window.probeStyle('opacity: 0.25;', JSON.parse(window.STYLE_NAMES))"
    )
    assert first["opacity"] != second["opacity"]


def test_every_drawn_opacity_sits_inside_the_published_band(browser: Browser):
    payload = state_payload("two_targets_two_runs")
    parts = draw_panel(browser, payload)
    drawn = with_part(parts, "applied-value")
    assert len(drawn) == len(payload["applied"])
    for cell in drawn:
        value = float(cell["style"]["opacity"])
        assert payload["opacity_floor"] <= value <= payload["opacity_ceiling"], cell


def test_the_panel_draws_no_colour_of_its_own(browser: Browser):
    """A colour drawn here would come from nothing the surface publishes."""
    parts = draw_panel(browser, state_payload("two_targets_two_runs"))
    grounds = {one["style"]["backgroundColor"] for one in parts}
    assert grounds == {"rgba(0, 0, 0, 0)"}, grounds
    assert len({one["style"]["color"] for one in parts}) == 1


def test_the_wiring_the_surface_publishes_reaches_the_page(browser: Browser):
    payload = state_payload("bare")
    parts = draw_panel(browser, payload)
    assert [one["attrs"]["data-name"] for one in with_part(parts, "action")] == list(
        payload["actions"]
    )
    assert [one["text"] for one in with_part(parts, "action")] == list(
        payload["actions"].values()
    )
    assert [one["text"] for one in with_part(parts, "timer-delay-ms")] == [
        str(one) for one in payload["timer_delays_ms"]
    ]
    assert with_part(parts, "bus-topic") == []
    assert with_part(parts, "signal") == []
    assert with_part(parts, "widget") == []


def test_the_empty_wiring_lists_still_publish_their_own_count(browser: Browser):
    """An empty list drawn as nothing at all cannot be told from a missing one."""
    parts = draw_panel(browser, BARE)
    for part in ("bus_topics", "signals", "widgets"):
        assert one_part(parts, part)["attrs"]["data-count"] == "0"
    assert one_part(parts, "call-list")["attrs"]["data-count"] == str(
        len(BARE["call_names"])
    )


def test_the_step_list_draws_every_step_one_run_left(browser: Browser):
    payload = state_payload("two_targets_two_runs")
    parts = draw_panel(browser, payload)
    assert [one["text"] for one in with_part(parts, "step")] == payload["calls"]
    assert [one["text"] for one in with_part(parts, "call-name")] == payload[
        "call_names"
    ]


def test_this_host_can_take_every_drawn_reading():
    """A drawn reading this host cannot take is a reading nobody ever took."""
    import importlib.util

    assert importlib.util.find_spec("PySide6.QtWebEngineWidgets") is not None
    assert importlib.util.find_spec("PySide6.QtQml") is not None
