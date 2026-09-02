"""The React Stack Tranches tab, against stack_tranches_tab_surface.py."""

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
from src.gui.main_tabs import stack_tranches_tab_surface as surface
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    new_engine,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "stack_tranches_tab.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body writes into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

API = "acervatorStackTranchesTab."
SETTER = "acervatorSetStackTranchesTab"

#: The merged pieces the page loads beside this module, needed at call time.
SHARED_MODULES = (WEB / "shared_widgets.js", WEB / "header_strip.js")

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 3
HOST_WIDTH_PX = 1200
HOST_HEIGHT_PX = 700

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
OTHER_COLOUR = "#7c1fa2"
UNKNOWN_BOT = "no-such-bot"

NOW = 1_000_000.0


def tranche(index: int, price: float, size: float, status: str, **rest: Any) -> dict:
    """One stored stack tranche, in the keys the tab surface reads."""
    found = {
        surface.INDEX_KEY: index,
        surface.PRICE_KEY: price,
        surface.SIZE_KEY: size,
        surface.STATUS_KEY: status,
        surface.VISIBLE_KEY: bool(index % 2),
        surface.OPENED_TS_KEY: NOW - 100.0 * index,
    }
    found.update(rest)
    return found


FOUR_TRANCHES = [
    tranche(1, 21.5, 0.5, surface.STATUS_PENDING, order_id="abc"),
    tranche(2, 22.5, 1.5, surface.STATUS_PENDING),
    tranche(3, 23.5, 2.5, surface.STATUS_FILLED, fill_price=23.4),
    tranche(4, 24.5, 3.5, surface.STATUS_CANCELLED),
]


def bot(tranches: Any = None, **rest: Any) -> dict:
    """One bot the tab reads, holding the clear report each path returns."""
    found = {
        "tranches": list(tranches or []),
        "created": 8,
        "discarded": 2,
        "reset_ts": NOW - 900_000.0,
        "symbol": "BTC-USD",
        "clear_report": {
            surface.REPORT_COUNT_KEY: 3,
            surface.REPORT_SIZE_KEY: 7.5,
            surface.REPORT_KEPT_KEY: 1,
        },
        "counters_report": {
            surface.REPORT_CLEARED_KEY: 10,
            surface.REPORT_BEFORE_KEY: {
                surface.REPORT_CREATED_KEY: 8,
                surface.REPORT_DISCARDED_KEY: 2,
            },
        },
    }
    found.update(rest)
    return found


YES = {"answer": surface.YES_ANSWER}

STATES: dict = {
    "fresh": [{"reset": True}],
    "empty": [{"reset": True, "now_ts": NOW, "bot": bot()}],
    "loaded": [{"reset": True, "now_ts": NOW, "bot": bot(FOUR_TRANCHES)}],
    "cleared": [
        {"reset": True, "now_ts": NOW, "bot": bot(FOUR_TRANCHES)},
        dict(YES, clear=True),
    ],
    "declined": [
        {"reset": True, "now_ts": NOW, "bot": bot(FOUR_TRANCHES)},
        {"clear": True, "answer": surface.NO_ANSWER},
    ],
    "counters": [
        {"reset": True, "now_ts": NOW, "bot": bot(FOUR_TRANCHES)},
        dict(YES, clear_counters=True),
    ],
    "counters_zero": [
        {
            "reset": True,
            "now_ts": NOW,
            "bot": bot(FOUR_TRANCHES, created=0, discarded=0),
        },
        dict(YES, clear_counters=True),
    ],
    "nothing": [
        {"reset": True, "now_ts": NOW, "bot": bot([FOUR_TRANCHES[0]])},
        dict(YES, clear=True),
    ],
}
STATE_NAMES = tuple(STATES)
DRAWN_STATES = ("empty", "loaded", "cleared", "counters_zero")


def as_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True))


def at_dotted(node: Any, path: Any) -> Any:
    """The value ``path`` names, each step a bag key or a list place."""
    for step in path:
        node = node[step]
    return node


def build(steps: list) -> dict:
    """One payload, each step driving the same tab in the order given."""
    found: dict = {}
    for step in steps:
        found = surface.view_model(step)
    return as_json(found)


def state_payload(name: str) -> dict:
    return build(STATES[name])


def token_payload() -> dict:
    return as_json(dss.view_model({}))


class JsRuntime(JsEngine):
    """A QJSEngine holding the tab module and the merged pieces beside it."""

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
    payload = state_payload("loaded")
    payload["only_on_the_surface"] = []
    js.push(payload)
    assert sorted(set(payload) - set(declared_fields(js))) == ["only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_answers_for(
    js: JsRuntime,
):
    payload = state_payload("loaded")
    assert payload.pop("reset_ts") is not None
    js.push(payload)
    assert sorted(set(declared_fields(js)) - set(payload)) == ["reset_ts"]


def test_the_whole_payload_check_names_one_changed_value(js: JsRuntime):
    payload = state_payload("loaded")
    payload["reset_ts"] += 1
    js.push(payload)
    original = state_payload("loaded")
    differing = sorted(
        name for name in original if js.called("field", name) != original[name]
    )
    assert differing == ["reset_ts"], f"the check named {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    report = js.push(payload)
    assert report["declared"] == {
        "fields": len(payload),
        "rows": payload["detail"]["row_count"],
        "summary": len(payload["summary_styles"]),
        "labels": len(payload["labels"]),
        "buttons": len(payload["actions"]),
        "actions": len(payload["actions"]),
        "answers": 2,
    }, state
    assert report["held"] == dict(
        report["declared"],
        rows=len(payload["detail"]["rows"]),
        summary=len(payload["summary_rows"]),
        labels=len(payload["summary_rows"]),
    ), state


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    payload = state_payload("loaded")
    declared = len(payload)
    del payload["accessible_name"]
    report = js.push(payload)
    assert report["declared"]["fields"] == declared
    assert report["held"]["fields"] == declared - 1
    assert [one["field"] for one in report["faults"]] == ["accessible_name"]


DROPPED_ROWS = {"rows": ("detail", "rows"), "summary": ("summary_rows",)}


@pytest.mark.parametrize("counted", sorted(DROPPED_ROWS))
def test_a_dropped_row_shortens_the_held_count_not_the_declared_count(
    js: JsRuntime, counted: str
):
    payload = state_payload("loaded")
    at_dotted(payload, DROPPED_ROWS[counted]).pop()
    report = js.push(payload)
    assert report["declared"][counted] == report["held"][counted] + 1


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
    payload = state_payload("loaded")
    payload["reset_ts"] = str(payload["reset_ts"])
    js.push(payload)
    expected = python_kinds(state_payload("loaded"))
    actual = js.json(API + "kinds()")
    assert sorted(p for p, k in expected.items() if actual.get(p) != k) == ["reset_ts"]


def test_the_type_walk_names_a_scalar_where_a_summary_row_belongs(js: JsRuntime):
    """A scalar where the payload lists a row must not read as that row."""
    payload = state_payload("loaded")
    payload["summary_rows"][1] = 7
    js.push(payload)
    actual = js.json(API + "kinds()")
    assert actual.get("summary_rows.1") == "number"
    assert "summary_rows.1.0" not in actual
    payload["summary_rows"][1] = [None, None]
    js.push(payload)
    assert js.json(API + "kinds()").get("summary_rows.1.0") == "null"


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
    """A live object is what the plain data walk on this payload must never find."""
    raw: dict = {}
    for step in STATES[state]:
        raw = surface.view_model(step)
    assert not_plain_data(raw) == [], f"{state} publishes {not_plain_data(raw)}"


def test_the_plain_data_walk_names_a_live_object_put_on_the_payload():
    raw = surface.view_model({"reset": True})
    raw["summary_rows"] = [[surface.StackTranchesTabModel()]]
    assert not_plain_data(raw) == ["summary_rows.0.0"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reads_no_value_that_is_not_plain_data(js: JsRuntime, state: str):
    js.push(state_payload(state))
    assert js.json(API + "notPlainData()") == []


def test_the_plain_data_check_names_a_function_bound_into_the_payload(js: JsRuntime):
    js.push(state_payload("loaded"))
    js.run(
        SETTER + "(Object.assign(" + API + "payload(), { reset_ts: function () {} }));"
    )
    assert js.json(API + "notPlainData()") == [{"path": "reset_ts", "kind": "function"}]


def shown_values() -> set:
    """Every string the tab paints or shows as a tooltip, from every state."""
    found: set = set()
    for name in STATE_NAMES:
        payload = state_payload(name)
        for row in payload["summary_rows"]:
            found |= {one for one in row if isinstance(one, str)}
        for side in ("clear_button", "counters_button"):
            found |= {payload[side]["text"], payload[side]["tooltip"]}
        detail = payload["detail"]
        found |= {detail["title"], detail["header_text"]} | set(detail["rows"])
        for box in payload["boxes"]:
            found |= {box["title"], box["text"]}
        found |= {payload["empty_label"]["text"], payload["summary_group"]["title"]}
        found |= set(payload["settled_lines"])
        found |= {payload["tab_label"], payload["refresh_status"]}
        found |= {one for one in [payload["outcome"]] if isinstance(one, str)}
        for bag in ("labels", "texts", "titles", "formats", "colours", "styles"):
            found |= {one for one in payload[bag].values() if isinstance(one, str)}
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

BARE = state_payload("fresh")
WITH_BOX = state_payload("cleared")

#: NAMED_WORDS lists every published string the module may write.
NAMED_WORDS = sorted(
    set(BARE)
    | set(BARE["actions"])
    | set(BARE["answers"])
    | set(BARE["clear_button"])
    | set(BARE["container"])
    | set(BARE["counters_button"])
    | set(BARE["detail"])
    | set(BARE["empty_label"])
    | set(BARE["icons"])
    | set(BARE["summary_group"])
    | set(WITH_BOX["boxes"][0])
    | {surface.METHOD}
)


def test_the_module_writes_no_number_colour_shown_value_or_token_value():
    """A literal typed here is a second source for a value the surface owns."""
    assert caught_by_scan(MODULE_SOURCE) == set(), (
        "stack_tranches_tab.js writes values of its own: numbers "
        f"{MODULE_LITERALS['numbers']}, colours {HEX_COLOUR.findall(MODULE_SOURCE)}, "
        f"shown {sorted(set(MODULE_LITERALS['strings']) & SHOWN_VALUES)}, tokens "
        f"{sorted(set(MODULE_LITERALS['strings']) & TOKEN_VALUES)}, slashes "
        f"{MODULE_LITERALS['slashes']}"
    )


def test_the_module_names_only_the_surface_words_it_must_read():
    written = sorted(set(MODULE_LITERALS["strings"]) & PUBLISHED_STRINGS)
    assert set(written) <= set(NAMED_WORDS), (
        "the module names published strings the list does not allow: "
        f"{sorted(set(written) - set(NAMED_WORDS))}"
    )


def test_every_named_word_is_a_name_and_not_a_value_the_tab_shows():
    overlap = sorted(set(NAMED_WORDS) & SHOWN_VALUES)
    assert not overlap, f"these named words are values the tab shows: {overlap}"


WRITTEN_LINES: dict = {
    "colour": 'var written = "' + OTHER_COLOUR + '";',
    "ratio_amber": 'var written = "' + surface.RATIO_AMBER + '";',
    "ratio_green": 'var written = "' + surface.RATIO_GREEN + '";',
    "row_label": 'var written = "' + surface.PENDING_ROW_LABEL + '";',
    "group_title": 'var written = "' + surface.SUMMARY_GROUP_TITLE + '";',
    "empty_note": 'var written = "' + surface.EMPTY_TEXT + '";',
    "em_dash": 'var written = "' + surface.NO_VALUE + '";',
    "button_words": 'var written = "' + surface.CLEAR_BUTTON_PLAIN_TEXT + '";',
    "header": 'var written = "' + surface.HEADER_TEXT + '";',
    "ratio_min": "var written = " + str(surface.RATIO_MIN_OPENED) + ";",
    "spacing": "var written = " + str(surface.CONTENT_SPACING_PX) + ";",
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
        runtime = JsRuntime(js.engine_of(), MODULE_SOURCE + line)
        assert runtime.json("typeof " + SETTER) == "function", kind


def payload_sheets(payload: dict) -> list:
    """Every style sheet the tab applies, from every place that carries one."""
    found = [payload["empty_label"]["style_sheet"], payload["detail"]["header_style"]]
    found += [
        payload[side]["style_sheet"] for side in ("clear_button", "counters_button")
    ]
    found += list(payload["summary_styles"])
    found += list(payload["detail"]["row_styles"])
    found += list(payload["styles"].values())
    return found


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_colour_the_tab_carries_is_swept_for_the_alpha_order_fault(
    js: JsRuntime, state: str
):
    """Every published colour is swept for the eight-digit shape Qt reads first."""
    payload = state_payload(state)
    js.push(payload)
    swept = list(payload["colours"].values())
    for sheet in payload_sheets(payload):
        swept += js.called("hexRuns", sheet)
    assert len(swept) >= len(payload["colours"])
    assert [
        one for one in js.json(API + "faults()") if one["fault"] == "swapped-alpha"
    ] == [], f"{state} carries a colour Qt would read alpha-first"


@pytest.mark.parametrize("name", ("ratio_red", "ratio_amber", "ratio_green"))
def test_the_alpha_sweep_names_one_colour_written_with_eight_digits(
    js: JsRuntime, name: str
):
    payload = state_payload("loaded")
    payload["colours"][name] = SWAPPED_ALPHA
    report = js.push(payload)
    swapped = [one for one in report["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["detail"] for one in swapped] == [SWAPPED_ALPHA]


def swap_nth_colour(sheet: str, at: int, value: str) -> str:
    """``sheet`` with only its ``at``-th colour replaced by ``value``."""
    seen = {"n": -1}

    def pick(match: Any) -> str:
        seen["n"] += 1
        return value if seen["n"] == at else match.group(0)

    found = HEX_COLOUR.sub(pick, sheet)
    assert found != sheet, f"no colour sits at {at} of {sheet}"
    return found


SWEPT_SHEETS: dict = {
    "the ground of a clear button": (("clear_button", "style_sheet"), 0, None),
    "the border of a clear button": (("clear_button", "style_sheet"), 2, None),
    "the disabled text of a clear button": (("clear_button", "style_sheet"), 3, None),
    "the disabled border of a clear button": (("clear_button", "style_sheet"), 4, None),
    "the ground of the counters button": (("counters_button", "style_sheet"), 0, None),
    "the empty note": (("empty_label", "style_sheet"), 0, None),
    "the detail header": (("detail", "header_style"), 0, None),
    "one painted summary row": (("summary_styles", 3), 0, "summary:3"),
    "one filled tranche row": (("detail", "row_styles", 2), 0, "row:2"),
}


@pytest.mark.parametrize("case", sorted(SWEPT_SHEETS))
def test_the_alpha_sweep_reads_a_colour_inside_one_style_sheet(
    js: JsRuntime, case: str
):
    """A colour inside a disabled block is one no declaration walk would reach."""
    path, at, where = SWEPT_SHEETS[case]
    payload = state_payload("loaded")
    node = at_dotted(payload, path[:-1])
    node[path[-1]] = swap_nth_colour(node[path[-1]], at, SWAPPED_ALPHA)
    report = js.push(payload)
    swapped = [one for one in report["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["detail"] for one in swapped] == [SWAPPED_ALPHA], case
    assert [one["where"] for one in swapped] == [where], case


def test_the_alpha_sweep_reads_a_gradient_no_browser_stylesheet_runs(js: JsRuntime):
    payload = state_payload("loaded")
    payload["empty_label"]["style_sheet"] = "background: qlineargradient(x1: 0);"
    report = js.push(payload)
    assert [one["fault"] for one in report["faults"] if one["fault"] == "not-css"] == [
        "not-css"
    ]


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
    payload = state_payload("loaded")
    payload["titles"]["0"] = payload["titles"]["clear_tranches"]
    report = js.push(payload)
    moved = [one for one in report["faults"] if one["fault"] == "reordered-key"]
    assert [one["detail"] for one in moved] == ["0"]


def test_the_wired_names_are_read_from_a_list_and_not_from_the_action_bag(
    js: JsRuntime,
):
    """Two buttons share one style, so a bag's key order would be their only order."""
    payload = state_payload("loaded")
    js.push(payload)
    assert js.json(API + "actionNames()") == list(payload["actions"])
    assert js.json(API + "buttonNames()") == list(payload["actions"])
    assert js.json(API + "buttonFields()") == ["clear_button", "counters_button"]


def test_the_action_check_names_a_wired_name_the_payload_never_declared(js: JsRuntime):
    payload = state_payload("loaded")
    payload["actions"]["no_such_signal"] = "nothing"
    report = js.push(payload)
    unknown = [one for one in report["faults"] if one["fault"] == "unknown-action"]
    assert [one["detail"] for one in unknown] == ["no_such_signal"]


def test_the_action_check_names_a_wired_name_the_payload_dropped(js: JsRuntime):
    payload = state_payload("loaded")
    dropped = list(payload["actions"])[1]
    del payload["actions"][dropped]
    report = js.push(payload)
    missing = [
        one
        for one in report["faults"]
        if one["fault"] == "missing" and one["field"] == "actions"
    ]
    assert [one["detail"] for one in missing] == [dropped]


@pytest.mark.parametrize("state", DRAWN_STATES)
def test_each_summary_row_is_found_by_its_own_label(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    for name, value in payload["summary_rows"]:
        assert js.called("summaryValue", name) == value


def test_the_label_bag_is_longer_than_the_rows_one_state_draws(js: JsRuntime):
    """Eight labels are published against seven drawn rows, so pairing is by name."""
    payload = state_payload("counters_zero")
    js.push(payload)
    assert len(payload["labels"]) == len(payload["summary_rows"]) + 1
    drawn = js.json(API + "drawnLabels()")
    published = js.json(API + "publishedLabels()")
    assert set(drawn) < set(published)
    absent = sorted(set(published) - set(drawn))
    assert absent == [surface.DISCARDED_ROW_LABEL]
    assert js.json(API + "faults()") == []


def test_each_summary_row_keeps_its_own_style_when_the_last_label_is_absent(
    js: JsRuntime,
):
    """Pairing by position would move the ratio colour onto the row above it."""
    payload = state_payload("counters_zero")
    js.push(payload)
    for at, (name, _value) in enumerate(payload["summary_rows"]):
        assert js.called("summaryStyleNamed", name) == payload["summary_styles"][at]
    assert (
        js.called("summaryStyleNamed", surface.PENDING_SIZE_ROW_LABEL)
        == surface.PENDING_SIZE_STYLE
    )


def test_the_label_check_names_a_row_whose_label_the_payload_never_published(
    js: JsRuntime,
):
    payload = state_payload("loaded")
    payload["summary_rows"][2][0] = LONG_NAME
    report = js.push(payload)
    unnamed = [one for one in report["faults"] if one["fault"] == "unnamed-row"]
    assert [one["where"] for one in unnamed] == ["summary:2"]


@pytest.mark.parametrize("state", ("loaded", "cleared", "nothing"))
def test_each_tranche_row_is_named_by_the_number_it_prints(js: JsRuntime, state: str):
    """A tranche row is the case where a position alone is not a name."""
    payload = state_payload(state)
    js.push(payload)
    named = js.json(API + "rowIdentities()")
    assert len(named) == payload["detail"]["row_count"]
    assert [one["name"] for one in named] == [
        line.strip().split(" ")[0] for line in payload["detail"]["rows"]
    ]
    for one in named:
        assert (
            js.called("detailRowNamed", one["name"])
            == payload["detail"]["rows"][one["at"]]
        )


def test_a_tranche_row_keeps_its_own_number_when_the_rows_arrive_reordered(
    js: JsRuntime,
):
    """Reordering renumbers no tranche, so each number keeps its own row."""
    payload = state_payload("loaded")
    js.push(payload)
    first = js.json(API + "rowIdentities()")
    payload["detail"]["rows"].reverse()
    payload["detail"]["row_styles"].reverse()
    js.push(payload)
    second = js.json(API + "rowIdentities()")
    assert sorted(one["name"] for one in first) == sorted(one["name"] for one in second)
    assert [one["name"] for one in first] != [one["name"] for one in second]


def test_the_identity_check_names_two_tranche_rows_printing_one_number(js: JsRuntime):
    payload = state_payload("loaded")
    payload["detail"]["rows"][1] = payload["detail"]["rows"][0]
    report = js.push(payload)
    duplicate = [one for one in report["faults"] if one["fault"] == "duplicate-name"]
    assert [one["where"] for one in duplicate] == ["row:1"]


@pytest.mark.parametrize("at", (0, 1))
def test_each_clear_button_runs_its_own_handler_with_its_own_name(
    js: JsRuntime, at: int
):
    """Two buttons share one style sheet, so only the argument tells them apart."""
    payload = state_payload("loaded")
    js.push(payload)
    name = list(payload["actions"])[at]
    js.bind_json("NAME", name)
    pressed = js.json(API + "press(JSON.parse(NAME), JSON.parse(NAME))")
    assert pressed["name"] == name
    assert pressed["argument"] == name
    assert pressed["action"] == payload["actions"][name]


def test_the_press_check_would_see_a_button_that_answered_with_another_name(
    js: JsRuntime,
):
    payload = state_payload("loaded")
    js.push(payload)
    names = list(payload["actions"])
    js.run(API + "press('" + names[0] + "', '" + names[1] + "');")
    assert js.json(API + "pressed()")["argument"] != names[0]


@pytest.mark.parametrize("name", ("yes", "no"))
def test_each_message_box_answer_carries_the_value_the_surface_publishes(
    js: JsRuntime, name: str
):
    payload = state_payload("cleared")
    js.push(payload)
    assert js.called("answerValue", name) == payload["answers"][name]
    assert js.json(API + "defaultAnswer()") == payload["answers"]["default"]


@pytest.mark.parametrize("state", ("cleared", "declined", "counters", "nothing"))
def test_each_message_box_offers_the_answers_its_own_icon_names(
    js: JsRuntime, state: str
):
    """Only the box Qt raised as a question carries a second answer."""
    payload = state_payload(state)
    js.push(payload)
    offered = js.json(API + "boxes()")
    assert offered, f"{state} raised no box"
    for at, box in enumerate(payload["boxes"]):
        asks = box["icon"] == payload["icons"]["question"]
        names = js.json(API + "boxAnswers(" + API + "boxes()[" + str(at) + "])")
        assert names == (["yes", "no"] if asks else ["no"]), f"{state} box {at}"


def test_the_answer_check_names_a_default_the_answer_bag_never_offers(js: JsRuntime):
    payload = state_payload("cleared")
    payload["answers"]["default"] = LONG_NAME
    report = js.push(payload)
    assert [
        one["field"] for one in report["faults"] if one["fault"] == "disagrees"
    ] == ["answers"]


def test_the_box_check_names_a_title_the_payload_never_published(js: JsRuntime):
    payload = state_payload("cleared")
    payload["boxes"][0]["title"] = LONG_NAME
    report = js.push(payload)
    unnamed = [one for one in report["faults"] if one["fault"] == "unnamed-row"]
    assert [one["where"] for one in unnamed] == ["box:0"]


@pytest.mark.parametrize("dropped", (True, False))
@pytest.mark.parametrize("name", sorted(BARE))
def test_a_field_the_payload_drops_or_nulls_is_reported_and_the_module_answers(
    js: JsRuntime, name: str, dropped: bool
):
    """A payload the surface would never send must report, never raise."""
    payload = state_payload("loaded")
    if dropped:
        del payload[name]
    else:
        payload[name] = None
    report = js.push(payload)
    assert isinstance(report["faults"], list), name
    if dropped:
        assert [
            one
            for one in report["faults"]
            if one["fault"] == "missing" and one["field"] == name
        ], name
    assert js.json(API + "isLoaded()") is True, name
    assert isinstance(js.json(API + "rowIdentities()"), list), name
    assert isinstance(js.json(API + "drawnLabels()"), list), name
    assert isinstance(js.json(API + "boxes()"), list), name
    assert isinstance(js.json(API + "kinds()"), dict), name


HOSTILE_VALUES: dict = {
    "a number where text belongs": ("refresh_status", 7),
    "text where a number belongs": ("pending_size_total", "a lot"),
    "nan": ("pending_size_total", "nan"),
    "inf": ("pending_size_total", "inf"),
    "minus inf": ("pending_size_total", "-inf"),
    "a huge integer": ("pending_size_total", 10**24),
    "a huge reset stamp": ("reset_ts", 10**24),
    "a two hundred character outcome": ("outcome", LONG_NAME),
    "markup in the outcome": ("outcome", MARKUP_NAME),
    "a newline in the outcome": ("outcome", NEWLINE_NAME),
    "summary rows is a bag": ("summary_rows", {}),
    "summary styles is text": ("summary_styles", "#123a63"),
    "detail is a list": ("detail", []),
    "boxes is text": ("boxes", "a box"),
    "labels is a list": ("labels", []),
    "answers is a list": ("answers", []),
    "actions is a list": ("actions", []),
    "colours is a list": ("colours", []),
    "clear button is a list": ("clear_button", []),
    "counters button is text": ("counters_button", "a button"),
    "empty label is a number": ("empty_label", 7),
    "styles is a list": ("styles", []),
    "icons is a list": ("icons", []),
    "titles is a list": ("titles", []),
}


@pytest.mark.parametrize("case", sorted(HOSTILE_VALUES))
def test_a_hostile_value_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    name, value = HOSTILE_VALUES[case]
    payload = state_payload("loaded")
    payload[name] = value
    report = js.push(payload)
    assert isinstance(report["faults"], list), case
    assert js.json(API + "isLoaded()") is True, case
    assert isinstance(js.json(API + "kinds()"), dict), case
    assert isinstance(js.json(API + "rowIdentities()"), list), case
    assert isinstance(js.json(API + "drawnLabels()"), list), case
    assert isinstance(js.json(API + "sheets()"), list), case


HOSTILE_ROWS: dict = {
    "a null row": None,
    "a scalar row": 7,
    "a bag row": {},
    "a two hundred character row": LONG_NAME,
    "markup": MARKUP_NAME,
    "a newline": NEWLINE_NAME,
    "an empty row": "",
}


@pytest.mark.parametrize("case", sorted(HOSTILE_ROWS))
def test_a_hostile_tranche_row_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    payload = state_payload("loaded")
    payload["detail"]["rows"][0] = HOSTILE_ROWS[case]
    report = js.push(payload)
    assert isinstance(report["faults"], list), case
    assert isinstance(js.json(API + "detailRows()"), list), case
    named = js.json(API + "rowIdentities()")
    assert len(named) == len(payload["detail"]["rows"]), case
    assert isinstance(js.json(API + "kinds()"), dict), case


HOSTILE_SUMMARY: dict = {
    "a null row": None,
    "a scalar row": 7,
    "a short row": ["Pending tranches:"],
    "a number where a label belongs": [7, 7],
    "a two hundred character label": [LONG_NAME, LONG_NAME],
    "markup": [MARKUP_NAME, MARKUP_NAME],
    "a newline": [NEWLINE_NAME, NEWLINE_NAME],
}


@pytest.mark.parametrize("case", sorted(HOSTILE_SUMMARY))
def test_a_hostile_summary_row_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    payload = state_payload("loaded")
    payload["summary_rows"][0] = HOSTILE_SUMMARY[case]
    report = js.push(payload)
    assert isinstance(report["faults"], list), case
    assert len(js.json(API + "drawnLabels()")) == len(payload["summary_rows"]), case
    assert isinstance(js.json(API + "kinds()"), dict), case


def test_two_summary_rows_carrying_one_label_are_both_kept_and_read_by_name(
    js: JsRuntime,
):
    """A duplicate label makes the later row the one a name finds."""
    payload = state_payload("loaded")
    payload["summary_rows"][1][0] = payload["summary_rows"][0][0]
    js.push(payload)
    assert len(js.json(API + "drawnLabels()")) == len(payload["summary_rows"])
    assert (
        js.called("summaryValue", payload["summary_rows"][0][0])
        == payload["summary_rows"][1][1]
    )


def test_a_bot_holding_no_tranche_at_all_draws_the_empty_note_and_no_detail(
    js: JsRuntime,
):
    """Zero tranches is the state the operator sees before the first SCRUM."""
    payload = state_payload("empty")
    js.push(payload)
    assert payload["detail"]["shown"] is False
    assert payload["empty_label"]["shown"] is True
    assert payload["detail"]["rows"] == []
    assert js.json(API + "rowIdentities()") == []
    assert js.json(API + "faults()") == []


def test_a_tranche_naming_a_bot_the_fleet_has_none_of_changes_no_drawn_row(
    js: JsRuntime,
):
    """The stack ledger stores no bot id, so an unknown one reaches no row."""
    named = [dict(one) for one in FOUR_TRANCHES]
    named[0]["bot_id"] = UNKNOWN_BOT
    payload = build([{"reset": True, "now_ts": NOW, "bot": bot(named)}])
    js.push(payload)
    assert payload["detail"]["rows"] == state_payload("loaded")["detail"]["rows"]
    assert UNKNOWN_BOT not in json.dumps(payload)
    assert js.json(API + "faults()") == []


def test_the_hostile_sweep_would_have_seen_a_module_that_stopped_answering(
    js: JsRuntime,
):
    """A module that raised on one hostile value would answer no row and no label."""
    js.push(7)
    assert js.json(API + "detailRows()") == []
    assert js.json(API + "rowIdentities()") == []
    assert js.json(API + "drawnLabels()") == []
    assert js.json(API + "isLoaded()") is False


def test_a_clear_leaves_the_live_order_count_of_the_path_that_did_not_run(
    js: JsRuntime,
):
    """The surface fills live_orders only inside the tranche clear, so it reads zero."""
    js.push(state_payload("counters"))
    assert js.called("bag", "counts")["live_orders"] == 0
    cleared = state_payload("cleared")
    js.push(cleared)
    assert js.called("bag", "counts")["live_orders"] == 1
    assert cleared["counts"]["droppable"] < cleared["detail"]["row_count"]


#: An empty tag pair a rich-text widget swallows and a plain one lays out.
MARKUP_PROBE = "<span></span>clear"
PLAIN_PROBE = "clear"


def laid_out(widget: Any) -> int:
    """The width one widget asks for to lay its caller text out."""
    return int(widget.minimumSizeHint().width())


def a_label(text: str) -> Any:
    from PySide6.QtWidgets import QLabel

    return QLabel(text)


def a_button(text: str) -> Any:
    from PySide6.QtWidgets import QPushButton

    return QPushButton(text)


def a_group(text: str) -> Any:
    from PySide6.QtWidgets import QGroupBox

    return QGroupBox(text)


def a_message(text: str) -> Any:
    from PySide6.QtWidgets import QMessageBox

    widget = QMessageBox()
    widget.setText(text)
    return widget


SCREEN_WIDGETS = {"QPushButton": a_button, "QGroupBox": a_group}
RICH_TEXT_WIDGETS = {"QLabel": a_label, "QMessageBox": a_message}
EVERY_WIDGET = dict(SCREEN_WIDGETS, **RICH_TEXT_WIDGETS)


@pytest.mark.parametrize("kind", sorted(SCREEN_WIDGETS))
def test_no_plain_widget_this_tab_uses_reads_its_caller_text_as_markup(qapp, kind: str):
    """A widget laying MARKUP_PROBE out wider than PLAIN_PROBE never read its tags."""
    assert qapp is not None
    build_widget = SCREEN_WIDGETS[kind]
    assert laid_out(build_widget(MARKUP_PROBE)) > laid_out(
        build_widget(PLAIN_PROBE)
    ), f"{kind} laid the markup out no wider than the plain words"


@pytest.mark.parametrize("kind", sorted(RICH_TEXT_WIDGETS))
def test_the_two_widgets_this_tab_uses_that_do_read_markup_are_named(qapp, kind: str):
    """QLabel and QMessageBox lay MARKUP_PROBE out exactly as wide as PLAIN_PROBE."""
    assert qapp is not None
    build_widget = RICH_TEXT_WIDGETS[kind]
    assert laid_out(build_widget(MARKUP_PROBE)) == laid_out(build_widget(PLAIN_PROBE))


@pytest.mark.parametrize("kind", sorted(EVERY_WIDGET))
def test_the_markup_measurement_reads_a_longer_text_as_a_wider_layout(qapp, kind: str):
    """A width that never moved would read every widget as one that reads markup."""
    assert qapp is not None
    build_widget = EVERY_WIDGET[kind]
    assert laid_out(build_widget(PLAIN_PROBE * 8)) > laid_out(build_widget(PLAIN_PROBE))


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
            "the page never defined the stack tranches tab module in "
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


STYLE_NAMES = [
    "color",
    "backgroundColor",
    "borderTopWidth",
    "borderTopColor",
    "borderTopStyle",
    "paddingTop",
    "fontWeight",
    "fontSize",
    "fontFamily",
    "whiteSpace",
    "gap",
]

PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = '" + str(HOST_WIDTH_PX) + "px';"
    "window.HOST.style.height = '" + str(HOST_HEIGHT_PX) + "px';"
    "window.HOST.setAttribute('data-part', 'stack-tranches-page');"
    "document.body.appendChild(window.HOST);"
    "window.PRESSED = [];"
    "window.readStyle = function (el, names) {"
    "  var computed = getComputedStyle(el);"
    "  var found = {};"
    "  names.forEach(function (n) { found[n] = computed[n]; });"
    "  return found; };"
    "window.probeAssign = function (style, names) {"
    "  var probe = document.createElement('div');"
    "  Object.keys(style).forEach(function (n) { probe.style[n] = style[n]; });"
    "  document.body.appendChild(probe);"
    "  var found = window.readStyle(probe, names);"
    "  probe.remove();"
    "  return found; };"
    "window.partNamed = function (name) {"
    "  return window.HOST.querySelector('[data-part=\"' + name + '\"]'); };"
    "window.partsNamed = function (name) {"
    "  return Array.prototype.slice.call("
    "    window.HOST.querySelectorAll('[data-part=\"' + name + '\"]')); };"
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
    "        title: el.title, hidden: el.hidden,"
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

WIRE_HANDLERS = (
    "window.HANDLERS = {"
    "  onClear: function (n) { window.PRESSED.push(['clear', n]); },"
    "  onAnswer: function (n) { window.PRESSED.push(['answer', n]); } };"
)


def draw_tab(browser: Browser, payload: dict) -> list:
    browser.js(PAGE_HELPERS)
    browser.js(WIRE_HANDLERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    browser.js(
        "acervatorSetTokens(JSON.parse(window.TOKENS));"
        "acervatorTokens.apply(document.documentElement);"
    )
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        SETTER
        + "(JSON.parse(window.PAYLOAD));"
        + API
        + "fill(window.HOST, null, window.HANDLERS);"
    )
    return json.loads(browser.js(READ_PARTS))


def at_path(parts: list, path: str) -> list:
    return [one for one in parts if one["path"] == path]


def with_part(parts: list, name: str) -> list:
    return [one for one in parts if one["path"].split("/")[-1] == name]


def probe_for(browser: Browser, style: dict) -> dict:
    return browser.parsed(
        "window.probeAssign(" + json.dumps(style) + ", JSON.parse(window.STYLE_NAMES))"
    )


def test_the_tab_fills_the_named_space_the_window_left_for_it(browser: Browser):
    """The Live Bot Settings window names one space and this tab fills it."""
    parts = draw_tab(browser, state_payload("loaded"))
    assert browser.parsed(API + "spacePart") == "stack-tranches-page"
    assert at_path(parts, "stack-tranches-tab"), "the tab drew nothing into the space"


def test_every_child_the_page_draws_carries_its_own_name(browser: Browser):
    """A drawn child with no data-part is one no check can read."""
    draw_tab(browser, state_payload("cleared"))
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named, f"{every - named} drawn children carry no data-part"
    assert named > 0


def test_the_named_child_check_would_see_one_unnamed_child(browser: Browser):
    draw_tab(browser, state_payload("cleared"))
    browser.js("window.HOST.firstChild.appendChild(document.createElement('span'));")
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named + 1


@pytest.mark.parametrize("state", DRAWN_STATES)
def test_each_summary_row_draws_the_label_and_value_the_surface_carries(
    browser: Browser, state: str
):
    payload = state_payload(state)
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "summary-value")
    assert len(drawn) == len(payload["summary_rows"])
    by_label = {one["attrs"]["data-key"]: one for one in drawn}
    labels = {
        one["attrs"]["data-key"]: one for one in with_part(parts, "summary-label")
    }
    for name, value in payload["summary_rows"]:
        assert by_label[name]["text"] == value, f"{state} row {name}"
        assert labels[name]["text"] == name


def test_each_painted_summary_row_matches_a_probe_built_from_its_whole_style(
    browser: Browser,
):
    """The applied value is read against a probe built from the whole declaration."""
    payload = state_payload("loaded")
    parts = draw_tab(browser, payload)
    by_label = {
        one["attrs"]["data-key"]: one for one in with_part(parts, "summary-value")
    }
    for at, (name, _value) in enumerate(payload["summary_rows"]):
        sheet = payload["summary_styles"][at]
        probe = probe_for(
            browser, browser.parsed(API + "paintedStyle(" + json.dumps(sheet) + ")")
        )
        found = by_label[name]["style"]
        assert found["color"] == probe["color"], f"{name} drew {found} against {probe}"
        assert found["fontWeight"] == probe["fontWeight"]
        assert found["fontSize"] == probe["fontSize"]


def test_the_rendered_comparison_would_see_one_repainted_summary_row(browser: Browser):
    parts = draw_tab(browser, state_payload("loaded"))
    drawn = with_part(parts, "summary-value")[0]
    probe = probe_for(browser, {"color": OTHER_COLOUR})
    assert drawn["style"]["color"] != probe["color"]


def test_an_unpainted_summary_row_takes_no_colour_at_all(browser: Browser):
    """The surface publishes an empty sheet for no colour, and it must not paint."""
    parts = draw_tab(browser, state_payload("loaded"))
    unpainted = [
        one
        for one in with_part(parts, "summary-value")
        if one["attrs"]["data-styled"] == "false"
    ]
    assert unpainted, "no summary row was left unpainted"
    plain = probe_for(browser, {})
    for one in unpainted:
        assert one["style"]["color"] == plain["color"]


def test_the_unpainted_check_would_see_a_row_the_surface_painted(browser: Browser):
    payload = state_payload("loaded")
    payload["summary_styles"] = [
        surface.RATIO_STYLE_FORMAT.format(colour=OTHER_COLOUR)
        for _ in payload["summary_styles"]
    ]
    parts = draw_tab(browser, payload)
    assert [
        one
        for one in with_part(parts, "summary-value")
        if one["attrs"]["data-styled"] == "false"
    ] == []


@pytest.mark.parametrize("state", ("loaded", "empty"))
def test_each_clear_button_draws_the_words_state_and_tooltip_the_surface_carries(
    browser: Browser, state: str
):
    payload = state_payload(state)
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "clear-button")
    assert [one["attrs"]["data-key"] for one in drawn] == [
        "clear_button",
        "counters_button",
    ]
    for one in drawn:
        side = payload[one["attrs"]["data-key"]]
        assert one["text"] == side["text"]
        assert one["title"] == side["tooltip"]
        assert one["attrs"]["data-enabled"] == str(side["enabled"]).lower()
        assert (
            one["attrs"]["data-action"] == payload["actions"][one["attrs"]["data-name"]]
        )


def test_each_clear_button_paints_the_sheet_the_surface_publishes(browser: Browser):
    """The border is read against a probe built from the whole declaration."""
    payload = state_payload("loaded")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "clear-button")[0]
    probe = probe_for(
        browser,
        browser.parsed(
            API + "paintedStyle(" + json.dumps(payload["styles"]["danger_button"]) + ")"
        ),
    )
    assert drawn["style"]["borderTopWidth"] == probe["borderTopWidth"]
    assert drawn["style"]["borderTopStyle"] == probe["borderTopStyle"]
    assert drawn["style"]["backgroundColor"] == probe["backgroundColor"]
    assert drawn["style"]["paddingTop"] == probe["paddingTop"]


@pytest.mark.parametrize("at", (0, 1))
def test_pressing_one_clear_button_runs_the_handler_with_its_own_wired_name(
    browser: Browser, at: int
):
    payload = state_payload("loaded")
    draw_tab(browser, payload)
    browser.js("window.partsNamed('clear-button')[" + str(at) + "].click();")
    assert browser.parsed("window.PRESSED") == [["clear", list(payload["actions"])[at]]]
    assert (
        browser.parsed(API + "pressed()")["action"]
        == list(payload["actions"].values())[at]
    )


def test_a_clear_button_the_surface_disables_is_drawn_disabled(browser: Browser):
    payload = state_payload("empty")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "clear-button")
    assert [one["attrs"]["data-enabled"] for one in drawn] == ["false", "true"]
    browser.js("window.partsNamed('clear-button')[0].click();")
    assert browser.parsed("window.PRESSED") == []


def test_pressing_one_message_box_answer_runs_the_handler_with_that_value(
    browser: Browser,
):
    payload = state_payload("cleared")
    draw_tab(browser, payload)
    browser.js("window.partsNamed('box-button')[0].click();")
    assert browser.parsed("window.PRESSED") == [["answer", payload["answers"]["yes"]]]


def test_the_handler_check_would_see_a_press_nobody_made(browser: Browser):
    draw_tab(browser, state_payload("cleared"))
    assert browser.parsed("window.PRESSED") == []


def test_each_message_box_draws_its_title_text_and_the_answers_it_offers(
    browser: Browser,
):
    payload = state_payload("cleared")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "message-box")
    assert len(drawn) == len(payload["boxes"])
    for at, box in enumerate(payload["boxes"]):
        assert drawn[at]["attrs"]["data-icon"] == box["icon"]
        assert drawn[at]["attrs"]["data-key"] == box["title"]
    assert with_part(parts, "box-text")[0]["text"] == payload["boxes"][0]["text"]
    assert [one["attrs"]["data-name"] for one in with_part(parts, "box-button")] == [
        "yes",
        "no",
        "no",
    ]


@pytest.mark.parametrize("state", ("loaded", "cleared"))
def test_each_tranche_row_draws_in_its_own_place_under_its_own_number(
    browser: Browser, state: str
):
    payload = state_payload(state)
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "detail-row")
    assert [one["text"] for one in drawn] == payload["detail"]["rows"]
    assert [one["attrs"]["data-name"] for one in drawn] == [
        line.strip().split(" ")[0] for line in payload["detail"]["rows"]
    ]


def test_a_tranche_row_keeps_the_spacing_the_monospace_table_lines_up_with(
    browser: Browser,
):
    """A browser would collapse the padded columns without the whole declaration."""
    payload = state_payload("loaded")
    parts = draw_tab(browser, payload)
    row = with_part(parts, "detail-row")[0]
    header = with_part(parts, "detail-header")[0]
    style = browser.parsed(
        API + "paintedStyle(" + json.dumps(payload["detail"]["row_styles"][0]) + ")"
    )
    style["whiteSpace"] = "pre"
    probe = probe_for(browser, style)
    assert row["style"]["whiteSpace"] == probe["whiteSpace"]
    assert row["style"]["fontFamily"] == probe["fontFamily"]
    assert header["text"] == payload["detail"]["header_text"]
    assert header["style"]["whiteSpace"] == probe["whiteSpace"]


def test_the_spacing_check_would_see_a_row_a_browser_had_collapsed(browser: Browser):
    draw_tab(browser, state_payload("loaded"))
    probe = probe_for(browser, {"whiteSpace": "normal"})
    row = with_part(draw_tab(browser, state_payload("loaded")), "detail-row")[0]
    assert row["style"]["whiteSpace"] != probe["whiteSpace"]


def test_a_filled_tranche_row_is_painted_apart_from_a_plain_one(browser: Browser):
    payload = state_payload("loaded")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "detail-row")
    assert drawn[0]["style"]["color"] != drawn[2]["style"]["color"]
    probe = probe_for(
        browser,
        browser.parsed(
            API + "paintedStyle(" + json.dumps(payload["detail"]["row_styles"][2]) + ")"
        ),
    )
    assert drawn[2]["style"]["color"] == probe["color"]


def test_the_empty_note_and_the_detail_panel_show_where_the_surface_shows_them(
    browser: Browser,
):
    empty = draw_tab(browser, state_payload("empty"))
    loaded = draw_tab(browser, state_payload("loaded"))
    assert with_part(empty, "empty-note")[0]["hidden"] is False
    assert with_part(empty, "detail-panel")[0]["hidden"] is True
    assert with_part(loaded, "empty-note")[0]["hidden"] is True
    assert with_part(loaded, "detail-panel")[0]["hidden"] is False
    assert (
        with_part(empty, "empty-note")[0]["text"]
        == state_payload("empty")["empty_label"]["text"]
    )


def test_the_tab_refuses_markup_a_hostile_summary_value_carries(browser: Browser):
    """React writes the tags as text, so no element reaches the document."""
    payload = state_payload("loaded")
    payload["summary_rows"][0][1] = MARKUP_NAME
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "summary-value")[0]
    assert drawn["text"] == MARKUP_NAME
    assert "<img" not in drawn["html"]
    assert browser.parsed("window.HOST.querySelectorAll('img').length") == 0


def test_the_tab_refuses_markup_a_hostile_message_box_carries(browser: Browser):
    payload = state_payload("cleared")
    payload["boxes"][0]["text"] = MARKUP_NAME
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "box-text")[0]
    assert drawn["text"] == MARKUP_NAME
    assert "<img" not in drawn["html"]


def test_the_markup_refusal_would_see_a_tag_the_page_did_run(browser: Browser):
    draw_tab(browser, state_payload("loaded"))
    browser.js("window.HOST.firstChild.insertAdjacentHTML('beforeend', '<img>');")
    assert browser.parsed("window.HOST.querySelectorAll('img').length") == 1


def test_a_two_hundred_character_tranche_row_widens_the_panel_rather_than_clipping(
    browser: Browser,
):
    """A CSS row grows to fit where Qt clips, so the width is reported."""
    payload = state_payload("loaded")
    payload["detail"]["rows"][0] = LONG_NAME
    wide = with_part(draw_tab(browser, payload), "detail-row")[0]
    narrow = with_part(draw_tab(browser, state_payload("loaded")), "detail-row")[0]
    assert wide["width"] >= narrow["width"]


def test_the_tab_declares_its_own_spacing_and_leaves_the_form_to_the_host(
    browser: Browser,
):
    """The surface sets a spacing and no margin, and says the host builds the form."""
    payload = state_payload("loaded")
    parts = draw_tab(browser, payload)
    tab = at_path(parts, "stack-tranches-tab")[0]
    assert (
        tab["attrs"]["data-margins-set"]
        == str(payload["container"]["margins_set"]).lower()
    )
    probe = probe_for(browser, {"gap": str(payload["container"]["spacing_px"]) + "px"})
    assert tab["style"]["gap"] == probe["gap"]
    group = with_part(parts, "summary-group")[0]
    assert (
        group["attrs"]["data-configured-by-host"]
        == str(payload["summary_group"]["configured_by_host"]).lower()
    )


def test_the_outcome_and_the_refresh_line_carry_what_the_clear_path_reported(
    browser: Browser,
):
    payload = state_payload("cleared")
    parts = draw_tab(browser, payload)
    assert with_part(parts, "outcome")[0]["text"] == payload["outcome"]
    assert with_part(parts, "refresh-status")[0]["text"] == payload["refresh_status"]
    assert [one["text"] for one in with_part(parts, "settled-line")] == payload[
        "settled_lines"
    ]
