"""The React Quick Routing matrix, against the surface that describes it."""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import quick_routing_surface as qrs
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    new_engine,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "quick_routing.js"
TOKENS_PATH = WEB / "design_tokens.js"
WIDGETS_PATH = WEB / "shared_widgets.js"
HEADER_PATH = WEB / "header_strip.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: One lock for the whole run, so no worker reads a swapped module.
LOCK_PATH = Path(tempfile.gettempdir()) / "acervator_quick_routing_swap.lock"
LOCK_ATTEMPTS = 400_000


@contextlib.contextmanager
def module_held(attempts: int = LOCK_ATTEMPTS):
    """Takes LOCK_PATH so one worker at a time swaps quick_routing.js."""
    handle = None
    for _ in range(attempts):
        try:
            handle = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            break
        except FileExistsError:
            continue
        except PermissionError:
            continue
    if handle is None:
        raise AssertionError(f"{LOCK_PATH} stayed taken for all {attempts} attempts")
    try:
        yield
    finally:
        os.close(handle)
        LOCK_PATH.unlink(missing_ok=True)


with module_held():
    MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

MODULE_LITERALS = js_literals(MODULE_SOURCE)

JS_TIMEOUT_MS = 30_000
SETTLE_MS = 500
NETWORK_SETTLE_MS = 1500
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 2

#: Wide enough that a never-shown view does not read every width as zero.
HOST_WIDTH_CSS = "900px"
HOST_HEIGHT_CSS = "300px"

#: Each Python type name against the JavaScript type the bridge gives it.
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

ALPHA = "bot-alpha"
BETA = "bot-beta"
GAMMA = "bot-gamma"
THREE_BOTS = [ALPHA, BETA, GAMMA]
SYMBOLS = {ALPHA: "BTC", BETA: "ETH", GAMMA: "SOL"}

REBUILD = qrs.REBUILD_STEP
CONNECT = qrs.CONNECT_STEP
DISCONNECT = qrs.DISCONNECT_STEP
DISCONNECT_ALL = qrs.DISCONNECT_ALL_STEP

MARKUP_TEXT = '<img src="file:///c:/windows/win.ini">'
LONG_NAME = "N" * 200
STEP_SOURCES, STEP_DESTS = qrs.CHECKED_PARAMS


def rebuild(bots: Any = None) -> list:
    return [[REBUILD, THREE_BOTS if bots is None else bots]]


#: STATES holds every state of the panel the surface can be driven into.
STATES = {
    "empty": {"reset": True},
    "scoped": {"tab": {"widget_symbols": SYMBOLS}, "steps": rebuild()},
    "ticked": {
        "tab": {"widget_symbols": SYMBOLS},
        "steps": rebuild(),
        STEP_SOURCES: [ALPHA],
        STEP_DESTS: [BETA],
    },
    "connected": {
        "tab": {"widget_symbols": SYMBOLS, "answers": [True]},
        "steps": rebuild() + [CONNECT],
        STEP_SOURCES: [ALPHA],
        STEP_DESTS: [BETA],
    },
    "refused_rate": {
        "tab": {"widget_symbols": SYMBOLS},
        "rate": "not a rate",
        "steps": rebuild() + [CONNECT],
        STEP_SOURCES: [ALPHA],
        STEP_DESTS: [BETA],
    },
    "refused_no_sources": {
        "tab": {"widget_symbols": SYMBOLS},
        "steps": rebuild() + [CONNECT],
    },
    "disconnected": {
        "tab": {"widget_symbols": SYMBOLS, "answers": [True]},
        "steps": rebuild() + [DISCONNECT],
        STEP_SOURCES: [ALPHA],
        STEP_DESTS: [BETA, GAMMA],
    },
    "cleared": {
        "tab": {
            "widget_symbols": SYMBOLS,
            "answers": [True],
            "cleared_pairs": [[ALPHA, BETA]],
        },
        "steps": rebuild() + [DISCONNECT_ALL],
    },
    "masked": {
        "tab": {"widget_symbols": SYMBOLS, "masked": True},
        "steps": rebuild(),
    },
    "scrolled": {
        "tab": {"widget_symbols": SYMBOLS},
        "source_scroll": 35,
        "dest_scroll": 12,
        "steps": rebuild() + rebuild(),
    },
    "save_refused": {
        "tab": {
            "widget_symbols": SYMBOLS,
            "answers": [True],
            "apply_refusal": "disk is full",
        },
        "steps": rebuild() + [CONNECT],
        STEP_SOURCES: [ALPHA],
        STEP_DESTS: [BETA],
    },
}
STATE_NAMES = tuple(STATES)
FULL_STATE = "connected"


def payload_for(params: dict) -> dict:
    """The surface answer for params, after one round trip through JSON."""
    qrs.view_model({"reset": True})
    return json.loads(json.dumps(qrs.view_model(dict(params)), ensure_ascii=True))


def state_payload(name: str) -> dict:
    return payload_for(STATES[name])


def token_payload() -> dict:
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


class JsRuntime(JsEngine):
    """A QJSEngine holding the routing module and a ``window`` global."""

    module_path = MODULE_PATH
    setter = "acervatorSetQuickRouting"

    def load_tokens(self) -> None:
        self.run(TOKENS_PATH.read_text(encoding="utf-8"))
        self.bind_json("TOKENS", token_payload())
        self.run("acervatorSetTokens(JSON.parse(TOKENS));")

    def load_widgets(self) -> None:
        self.run(WIDGETS_PATH.read_text(encoding="utf-8"))

    def load_header(self) -> None:
        self.run(HEADER_PATH.read_text(encoding="utf-8"))

    def named(self, answerer: str, name: Any) -> Any:
        self.bind_json("NAME", name)
        return self.json("acervatorQuickRouting." + answerer + "(JSON.parse(NAME))")

    def field(self, name: str) -> Any:
        return self.named("field", name)


@pytest.fixture()
def bare(qapp) -> JsRuntime:
    """A JsRuntime holding the module with no shared module beside it."""
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


@pytest.fixture()
def js(bare: JsRuntime) -> JsRuntime:
    bare.load_widgets()
    bare.load_header()
    return bare


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(js: JsRuntime, state):
    payload = state_payload(state)
    js.push(payload)
    declared = js.json("acervatorQuickRouting.declaredNames()")
    missing = sorted(set(payload) - set(declared))
    assert not missing, f"{len(missing)} published fields have no answer: {missing}"
    extra = sorted(set(declared) - set(payload))
    assert not extra, f"the module declares fields the surface has none of: {extra}"
    differing = sorted(name for name in payload if js.field(name) != payload[name])
    assert not differing, (
        f"{state}: {len(differing)} of {len(payload)} published fields differ: "
        f"{differing}"
    )


def test_the_whole_payload_check_names_a_field_only_the_surface_holds(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["only_on_the_surface"] = []
    js.push(payload)
    declared = js.json("acervatorQuickRouting.declaredNames()")
    assert sorted(set(payload) - set(declared)) == ["only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_declares(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload.pop("tooltips")
    js.push(payload)
    declared = js.json("acervatorQuickRouting.declaredNames()")
    assert sorted(set(declared) - set(payload)) == ["tooltips"]


def test_the_field_value_check_names_one_changed_field(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["scope_ids"] = payload["scope_ids"] + ["bot-invented"]
    js.push(payload)
    shipped = state_payload(FULL_STATE)
    differing = sorted(name for name in shipped if js.field(name) != shipped[name])
    assert differing == ["scope_ids"], f"the check named {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(js: JsRuntime, state):
    payload = state_payload(state)
    report = js.push(payload)
    columns = payload["names"]["columns"]
    rows = sum(len(payload["rows"][name]) for name in columns)
    assert report["declared"]["fields"] == len(payload)
    assert report["held"]["fields"] == len(payload)
    assert report["declared"]["rows"] == len(columns) * len(payload["scope_ids"])
    assert report["held"]["rows"] == rows
    assert report["declared"]["buttons"] == len(payload["wiring"]["button_keys"])
    assert report["held"]["buttons"] == len(payload["texts"]["buttons"])


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    whole = len(payload)
    del payload["tooltips"]
    report = js.push(payload)
    assert report["declared"]["fields"] == whole
    assert report["held"]["fields"] == whole - 1


def test_a_row_the_surface_left_out_shortens_only_the_held_row_count(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["rows"]["source"] = payload["rows"]["source"][:-1]
    report = js.push(payload)
    assert report["declared"]["rows"] == report["held"]["rows"] + 1


def test_a_missing_bag_member_shortens_only_the_held_nested_count(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    whole = js.push(payload)["declared"]["nested"]
    del payload["layout"]["outer_spacing"]
    report = js.push(payload)
    assert report["declared"]["nested"] == whole
    assert report["held"]["nested"] == whole - 1
    named = [one for one in report["faults"] if one["field"] == "outer_spacing"]
    assert named and named[0]["fault"] == "missing", report["faults"]


def walk_payload(node: Any, keys: set, values: set) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            keys.add(key)
            walk_payload(value, keys, values)
        return
    if isinstance(node, list):
        for one in node:
            walk_payload(one, keys, values)
        return
    if isinstance(node, str):
        values.add(node)


def published() -> tuple:
    keys: set = set()
    values: set = set()
    for name in STATE_NAMES:
        walk_payload(state_payload(name), keys, values)
    values.discard("")
    keys.discard("")
    return keys, values


def as_css(value: Any) -> set:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return {str(value)}
    return {str(value), str(value) + "px"}


def token_values() -> set:
    found: set = set()
    for value in dss.TOKENS.values():
        found |= as_css(value)
    found.discard("")
    return found


PUBLISHED_KEYS, PUBLISHED_VALUES = published()

#: AMBIGUOUS is every string that is both a key name and a painted value.
AMBIGUOUS = PUBLISHED_KEYS & PUBLISHED_VALUES
PAINTED_VALUES = PUBLISHED_VALUES - AMBIGUOUS - {qrs.METHOD}
TOKEN_VALUES = token_values()


def test_no_number_is_written_in_the_module():
    assert not MODULE_LITERALS[
        "numbers"
    ], f"quick_routing.js holds numeric literals: {MODULE_LITERALS['numbers']}"


def test_no_colour_is_written_in_the_module():
    found = sorted(one for one in MODULE_LITERALS["strings"] if HEX_COLOUR.search(one))
    assert not found, f"quick_routing.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_panel_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & PAINTED_VALUES)
    assert not written, f"quick_routing.js writes panel values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"quick_routing.js writes token values: {written}"


def test_no_slash_stands_outside_a_comment_in_the_module():
    assert not MODULE_LITERALS["slashes"], (
        "quick_routing.js holds a slash outside a comment, which the scan "
        f"cannot read: {MODULE_LITERALS['slashes']}"
    )


PLANTS = {
    "number": "var written = 12;",
    "colour": 'var written = "' + qrs.LIST_SURFACE + '";',
    "painted": 'var written = "' + qrs.CONNECT_TEXT + '";',
    "slash": "var written = 8 " + chr(47) + " 2;",
}


@pytest.mark.parametrize("kind", sorted(PLANTS))
def test_the_literal_scan_reports_one_value_written_into_the_real_module(kind: str):
    """One value at a time goes into the shipped module and must be caught."""
    original = MODULE_SOURCE.encode("utf-8")
    before = hashlib.sha256(original).hexdigest()
    with module_held():
        try:
            swap_module(MODULE_PATH, original + b"\n" + PLANTS[kind].encode("utf-8"))
            found = js_literals(MODULE_PATH.read_text(encoding="utf-8"))
        finally:
            swap_module(MODULE_PATH, original)
        after = hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()
    assert after == before, "the module did not come back byte for byte"
    if kind == "number":
        assert found["numbers"], "a written number was not reported"
    elif kind == "slash":
        assert found["slashes"], "a written slash was not reported"
    elif kind == "colour":
        assert [one for one in found["strings"] if HEX_COLOUR.search(one)]
    else:
        assert set(found["strings"]) & PAINTED_VALUES


def python_kinds(node: Any, prefix: str = "") -> dict:
    """Every value's JavaScript type by dotted path, scalars included."""
    found: dict = {}
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            found[path] = JS_TYPE_OF[type(value).__name__]
            found.update(python_kinds(value, path))
        return found
    if isinstance(node, list):
        for at, one in enumerate(node):
            path = f"{prefix}.{at}"
            found[path] = JS_TYPE_OF[type(one).__name__]
            found.update(python_kinds(one, path))
    return found


@pytest.mark.parametrize("state", STATE_NAMES)
def test_both_sides_agree_by_type_at_every_path(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    theirs = python_kinds(payload)
    mine = js.json("acervatorQuickRouting.kinds()")
    missing = sorted(set(theirs) - set(mine))
    assert not missing, f"{state}: the module reads no type at {missing[:6]}"
    extra = sorted(set(mine) - set(theirs))
    assert not extra, f"{state}: the module invented paths {extra[:6]}"
    differing = sorted(one for one in theirs if theirs[one] != mine[one])
    assert not differing, f"{state}: types differ at {differing[:6]}"


@pytest.mark.parametrize("name", ["calls", "scope_ids", "stops"])
def test_a_scalar_where_a_list_belongs_is_named(js: JsRuntime, name: str):
    """A scalar slips past a member walk, so its own field is named."""
    payload = state_payload(FULL_STATE)
    payload[name] = 7
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "not-a-list"]
    assert [one["field"] for one in named] == [name], report["faults"]
    assert named[0]["detail"] == "number"


@pytest.mark.parametrize("name", ["layout", "rows", "tab", "wiring"])
def test_a_scalar_where_a_bag_belongs_is_named(js: JsRuntime, name: str):
    payload = state_payload(FULL_STATE)
    payload[name] = 7
    report = js.push(payload)
    named = [
        one
        for one in report["faults"]
        if one["fault"] == "not-an-object" and one["field"] == name
    ]
    assert named, report["faults"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_shape_check_is_quiet_on_a_shipped_payload(js: JsRuntime, state: str):
    report = js.push(state_payload(state))
    named = [
        one
        for one in report["faults"]
        if one["fault"] in ("not-a-list", "not-an-object")
    ]
    assert named == [], f"{state}: a shipped shape was refused: {named}"


def test_the_type_walk_names_a_null_inside_a_list(js: JsRuntime):
    """A scalar inside scope_ids is the hole eight units found."""
    payload = state_payload(FULL_STATE)
    payload["scope_ids"] = [None]
    js.push(payload)
    assert js.json("acervatorQuickRouting.kinds()")["scope_ids.0"] == "null"


def test_the_type_walk_names_a_scalar_where_a_bag_belongs(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["layout"] = 7
    js.push(payload)
    assert js.json("acervatorQuickRouting.kinds()")["layout"] == "number"


def test_the_type_check_names_one_changed_type(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["rate"]["min_pct"] = "0"
    js.push(payload)
    assert js.json("acervatorQuickRouting.kinds()")["rate.min_pct"] == "string"


#: NUMERIC_NAMES are bot names a JavaScript object reorders as keys.
NUMERIC_NAMES = ["7", "3", "1"]


@pytest.mark.parametrize("column", list(qrs.COLUMN_NAMES))
def test_the_row_order_is_the_order_the_surface_sent(js: JsRuntime, column: str):
    payload = payload_for(
        {"tab": {"widget_symbols": SYMBOLS}, "steps": rebuild(NUMERIC_NAMES)}
    )
    js.push(payload)
    assert js.named("rowOrder", column) == NUMERIC_NAMES


def test_the_symbol_bag_order_survives_bot_names_a_bag_reorders(js: JsRuntime):
    payload = payload_for(
        {
            "tab": {"widget_symbols": {name: name for name in NUMERIC_NAMES}},
            "steps": rebuild(NUMERIC_NAMES),
        }
    )
    js.push(payload)
    assert js.named("symbolOrder", "widget_symbols") == NUMERIC_NAMES


def test_reading_the_symbol_bag_keys_loses_the_order(js: JsRuntime):
    """The bag walk is what #276 breaks, so the order list must be read."""
    payload = payload_for(
        {
            "tab": {"widget_symbols": {name: name for name in NUMERIC_NAMES}},
            "steps": rebuild(NUMERIC_NAMES),
        }
    )
    js.push(payload)
    keys = js.json("Object.keys(acervatorQuickRouting.bag('tab').widget_symbols)")
    assert keys != NUMERIC_NAMES, "the bag kept the order, so this proves nothing"
    assert sorted(keys) == sorted(NUMERIC_NAMES)


def test_the_action_order_is_a_list_the_surface_owns(js: JsRuntime):
    js.push(state_payload(FULL_STATE))
    assert js.json("acervatorQuickRouting.actionOrder()") == list(qrs.ACTION_ORDER)
    assert js.json("acervatorQuickRouting.buttonKeys()") == list(qrs.BUTTON_KEYS)


def test_a_tick_is_read_by_name_and_not_by_row_position(js: JsRuntime):
    payload = state_payload("ticked")
    payload["rows"]["source"].reverse()
    js.push(payload)
    assert js.named("checked", "source") == [ALPHA]


def test_the_colour_refusal_names_an_eight_digit_hex(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["colors"]["list_surface"] = "#80ff00cc"
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "qt-colour"]
    assert named, "the module named no eight-digit colour"
    assert named[0]["detail"] == "AARRGGBB"


def test_the_colour_refusal_names_a_byte_alpha_in_a_sheet(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["styles"]["rate_zone"] = "QFrame{background:rgba(1,2,3,128);}"
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "qt-colour"]
    assert named, "the module named no byte alpha"
    assert named[0]["detail"] == "rgba("


def test_the_colour_refusal_is_quiet_on_a_shipped_payload(js: JsRuntime):
    report = js.push(state_payload(FULL_STATE))
    named = [one for one in report["faults"] if one["fault"] == "qt-colour"]
    assert named == [], f"a shipped colour was refused: {named}"


def test_a_refused_colour_is_left_out_of_the_style_the_module_paints(js: JsRuntime):
    kept = js.named("keptSheet", "QFrame{color:#80ff00cc;background:#101010;}")
    assert "#80ff00cc" not in kept
    assert "#101010" in kept


def test_a_row_label_carrying_a_tag_is_named(js: JsRuntime):
    payload = payload_for(
        {
            "tab": {"widget_symbols": {ALPHA: MARKUP_TEXT}},
            "steps": rebuild([ALPHA]),
        }
    )
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "markup"]
    assert named, f"a row label carrying a tag was not named: {report['faults']}"


def test_the_rate_the_operator_typed_carrying_a_tag_is_named(js: JsRuntime):
    payload = payload_for({"reset": True, "rate": MARKUP_TEXT})
    report = js.push(payload)
    named = [one for one in report["faults"] if one["field"] == "text"]
    assert named and named[0]["fault"] == "markup", report["faults"]


def test_the_markup_check_is_quiet_on_a_shipped_payload(js: JsRuntime):
    report = js.push(state_payload(FULL_STATE))
    named = [one for one in report["faults"] if one["fault"] == "markup"]
    assert named == [], f"shipped text was named as markup: {named}"


def test_a_route_naming_a_bot_that_does_not_exist_is_named(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["tab"]["saved"][0][0][0][1] = "bot-nowhere"
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "unknown-bot"]
    assert named, f"a wire to a bot out of scope was not named: {report['faults']}"
    assert named[0]["field"] == "bot-nowhere"


def test_the_unknown_bot_check_is_quiet_when_every_end_is_in_scope(js: JsRuntime):
    report = js.push(state_payload(FULL_STATE))
    named = [one for one in report["faults"] if one["fault"] == "unknown-bot"]
    assert named == [], f"an in-scope wire was named: {named}"


def test_the_module_reads_a_tick_the_surface_disagrees_with(js: JsRuntime):
    payload = state_payload("ticked")
    payload["selected"]["sources"] = [GAMMA]
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "disagrees"]
    assert named, f"the two tick lists differ and were not named: {report['faults']}"


HOSTILE: dict = {
    "rate_missing": ("rate", None),
    "rate_null": ("rate", None),
    "scope_ids_null": ("scope_ids", None),
    "rows_null": ("rows", None),
    "rows_number": ("rows", 7),
    "layout_text": ("layout", "wide"),
    "stops_number": ("stops", 3),
    "tab_null": ("tab", None),
    "wiring_list": ("wiring", []),
    "names_number": ("names", 1),
}

HOSTILE_RATES = {
    "nan": float("nan"),
    "inf": float("inf"),
    "minus_inf": float("-inf"),
    "huge": 10**24,
    "text_where_a_number_belongs": "twenty five",
    "number_where_text_belongs": 25,
    "a_newline": "2\n5",
    "markup": MARKUP_TEXT,
    "long_name": LONG_NAME,
}


@pytest.mark.parametrize("case", sorted(HOSTILE))
def test_a_hostile_top_level_field_still_answers(js: JsRuntime, case: str):
    payload = state_payload(FULL_STATE)
    name, value = HOSTILE[case]
    if case.endswith("_missing"):
        del payload[name]
    else:
        payload[name] = value
    report = js.push(payload)
    assert isinstance(report["faults"], list), f"{case} answered no fault list"
    assert report["held"]["fields"] <= report["declared"]["fields"]


@pytest.mark.parametrize("case", sorted(HOSTILE_RATES))
def test_a_hostile_rate_still_answers(js: JsRuntime, case: str):
    raw = HOSTILE_RATES[case]
    if isinstance(raw, float) and (math.isnan(raw) or math.isinf(raw)):
        raw = str(raw)
    payload = payload_for(
        {
            "tab": {"widget_symbols": SYMBOLS, "answers": [True]},
            "rate": raw,
            "steps": rebuild() + [CONNECT],
            STEP_SOURCES: [ALPHA],
            STEP_DESTS: [BETA],
        }
    )
    report = js.push(payload)
    assert isinstance(report["faults"], list), f"{case} answered no fault list"
    assert js.field("stops") == payload["stops"], f"{case} lost the stopping point"


@pytest.mark.parametrize("case", sorted(HOSTILE_RATES))
def test_a_hostile_bot_name_still_draws_every_row(js: JsRuntime, case: str):
    raw = HOSTILE_RATES[case]
    if isinstance(raw, float) and (math.isnan(raw) or math.isinf(raw)):
        raw = str(raw)
    payload = payload_for(
        {
            "tab": {"widget_symbols": {ALPHA: raw}},
            "steps": rebuild([ALPHA, ALPHA]),
        }
    )
    js.push(payload)
    assert len(js.named("rowOrder", "source")) == len(payload["rows"]["source"])


def test_a_payload_that_is_not_an_object_is_named(js: JsRuntime):
    report = js.json("acervatorSetQuickRouting(7)")
    assert report["declared"] is None
    assert report["faults"][0]["fault"] == "not-an-object"


def test_the_hostile_check_would_see_a_module_that_raised(js: JsRuntime):
    """A raise inside the module reaches js.json as an error, not a pass."""
    result = js.json(
        "(function () { try { return null.x; } catch (e) { return 1; } })()"
    )
    assert result == 1


class Browser:
    """The renderer page loaded from disk into a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        self.open_page()
        self.wait_for_module()

    def open_page(self) -> None:
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
                if self.js("typeof window.acervatorSetQuickRouting") == "function":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the routing module: readyState "
            + str(self.js("document.readyState"))
            + ", scripts "
            + str(self.js("document.scripts.length"))
            + ", header "
            + str(self.js("typeof window.acervatorHeader"))
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
    """A Browser page, or a skip where Chromium ships with no Qt."""
    assert qapp is not None
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    page = Browser()
    yield page
    page.close()


STYLE_NAMES = [
    "display",
    "flexDirection",
    "alignItems",
    "flexGrow",
    "flexShrink",
    "flexBasis",
    "rowGap",
    "columnGap",
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "color",
    "backgroundColor",
    "fontSize",
    "fontFamily",
    "fontWeight",
    "whiteSpace",
    "overflowX",
    "overflowY",
    "textOverflow",
    "textAlign",
    "userSelect",
    "cursor",
    "minWidth",
    "width",
    "borderTopStyle",
    "borderTopWidth",
    "borderTopColor",
]

#: EXPANDED holds each Qt shorthand against the computed names it settles into.
EXPANDED = {
    "border": ("borderTopStyle", "borderTopWidth", "borderTopColor"),
    "padding": ("paddingLeft", "paddingTop", "paddingRight", "paddingBottom"),
    "background": ("backgroundColor",),
    "background-color": ("backgroundColor",),
    "font-size": ("fontSize",),
    "font-weight": ("fontWeight",),
    "font-family": ("fontFamily",),
    "color": ("color",),
}

WATCH_VIOLATIONS = (
    "window.VIOLATIONS = [];"
    "document.addEventListener('securitypolicyviolation', function (e) {"
    "  window.VIOLATIONS.push(e.violatedDirective + ' ' + e.blockedURI); });"
)

PAGE_HELPERS = (
    "window.HOST = document.getElementById('routing-host');"
    "if (window.HOST === null) {"
    "  window.HOST = document.createElement('div');"
    "  window.HOST.id = 'routing-host';"
    "  document.body.appendChild(window.HOST); }"
    "window.HOST.style.width = " + json.dumps(HOST_WIDTH_CSS) + ";"
    "window.HOST.style.height = " + json.dumps(HOST_HEIGHT_CSS) + ";"
    "window.HOST.style.display = 'flex';"
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
    "      var own = '';"
    "      Array.prototype.slice.call(el.childNodes).forEach(function (n) {"
    "        if (n.nodeType === Node.TEXT_NODE) { own += n.nodeValue; } });"
    "      found.push({ path: here, tag: el.tagName, attrs: attrs,"
    "        width: el.clientWidth, height: el.clientHeight,"
    "        room: el.scrollWidth, text: own, html: el.innerHTML,"
    "        children: el.children.length,"
    "        style: window.readStyle(el, names) });"
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


def draw_matrix(browser: Browser, payload: dict) -> list:
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetQuickRouting(JSON.parse(window.PAYLOAD));"
        "acervatorQuickRouting.renderMatrix(window.HOST);"
    )
    return json.loads(browser.js(READ_PARTS))


def python_declarations(body: str) -> list:
    found = []
    for part in str(body).split(";"):
        head, sep, tail = part.partition(":")
        if sep and head.strip() and tail.strip():
            found.append((head.strip(), tail.strip()))
    return found


def probe(browser: Browser, body: str) -> dict:
    """The computed style a probe takes from one whole declaration body."""
    names: list = []
    for prop, _ in python_declarations(body):
        names.extend(EXPANDED.get(prop, (prop,)))
    if not names:
        return {}
    return browser.parsed(
        "window.probeStyle("
        + json.dumps(body)
        + ", "
        + json.dumps(sorted(set(names)))
        + ")"
    )


def qt_block(sheet: str, selector: str) -> str:
    """The body of one Qt block, taken from the surface's own sheet."""
    for chunk in str(sheet).split("}"):
        head, sep, body = chunk.partition("{")
        if sep and head.strip() == selector:
            return body
    return ""


def at_path(parts: list, path: str) -> list:
    return [one for one in parts if one["path"] == path]


def only(parts: list, path: str) -> dict:
    found = at_path(parts, path)
    assert len(found) == 1, f"{len(found)} parts at {path}"
    return found[0]


def named(parts: list, path: str, key: str) -> dict:
    found = [one for one in at_path(parts, path) if one["attrs"].get("data-key") == key]
    assert len(found) == 1, f"{len(found)} parts at {path} named {key}"
    return found[0]


def in_column(parts: list, path: str, column: str) -> list:
    """Every part at one path belonging to the named column."""
    return [
        one for one in at_path(parts, path) if one["attrs"].get("data-column") == column
    ]


def one_in_column(parts: list, path: str, column: str) -> dict:
    found = in_column(parts, path, column)
    assert len(found) == 1, f"{len(found)} parts at {path} in {column}"
    return found[0]


def sheet_agrees(drawn: dict, expected: dict, where: str) -> None:
    assert expected, f"{where}: the probe took no value, so this compares nothing"
    differing = {
        name: (value, drawn["style"].get(name))
        for name, value in expected.items()
        if drawn["style"].get(name) != value
    }
    assert not differing, f"{where}: wanted against drawn {differing}"


MATRIX = "quick-routing"
COLUMNS = MATRIX + "/columns"
SOURCE_LIST = COLUMNS + "/bot-list"
RATE_ZONE = COLUMNS + "/rate-zone"
RATE_INPUT = RATE_ZONE + "/rate-input"
RATE_LABEL = RATE_ZONE + "/rate-label"
BUTTON_ROW = MATRIX + "/button-row"
BUTTONS = BUTTON_ROW + "/action-button"
ROWS = SOURCE_LIST + "/list-row"
ROW_LABEL = ROWS + "/row-label"


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    assert browser.js("typeof window.acervatorQuickRouting") == "object"
    assert browser.js("typeof window.acervatorSetQuickRouting") == "function"
    assert browser.js("typeof window.acervatorLoadQuickRouting") == "function"
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_module_makes_no_network_call_of_its_own(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    draw_matrix(browser, state_payload(FULL_STATE))
    browser.settle(SETTLE_MS)
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_page_refuses_a_network_call_when_one_is_made(browser: Browser):
    """The refusal check would be silent if the page allowed a fetch."""
    browser.js(WATCH_VIOLATIONS)
    browser.js(
        "window.PROBE = 'pending';"
        "fetch('https://example.invalid/x')"
        "  .then(function () { window.PROBE = 'allowed'; })"
        "  .catch(function (e) { window.PROBE = 'refused ' + e.message; });"
    )
    browser.settle(NETWORK_SETTLE_MS)
    assert str(browser.js("window.PROBE")).startswith("refused")


def test_every_drawn_element_carries_a_name(browser: Browser):
    draw_matrix(browser, state_payload(FULL_STATE))
    counts = browser.parsed(
        "[window.HOST.querySelectorAll('*').length,"
        " window.HOST.querySelectorAll('[data-part]').length]"
    )
    assert counts[0] == counts[1], f"{counts[0]} elements, {counts[1]} named"
    assert counts[0] > 0, "the matrix drew nothing at all"


def test_the_name_check_would_see_an_element_with_no_name(browser: Browser):
    draw_matrix(browser, state_payload(FULL_STATE))
    counts = browser.parsed(
        "(function () {"
        "  window.HOST.firstChild.appendChild(document.createElement('b'));"
        "  return [window.HOST.querySelectorAll('*').length,"
        "    window.HOST.querySelectorAll('[data-part]').length]; })()"
    )
    assert counts[0] == counts[1] + 1


def test_the_list_sheet_reaches_the_drawn_list(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_matrix(browser, payload)
    body = qt_block(payload["styles"]["list"], "QListWidget")
    sheet_agrees(
        one_in_column(parts, SOURCE_LIST, qrs.SOURCE_COLUMN),
        probe(browser, body),
        "the source list",
    )


def test_the_row_sheet_reaches_every_drawn_row(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_matrix(browser, payload)
    body = qt_block(payload["styles"]["list"], "QListWidget::item")
    wanted = probe(browser, body)
    for one in at_path(parts, ROWS):
        sheet_agrees(one, wanted, "row " + str(one["attrs"].get("data-key")))


def test_the_rate_input_sheet_reaches_the_drawn_input(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_matrix(browser, payload)
    body = qt_block(payload["styles"]["rate_input"], "QLineEdit")
    sheet_agrees(only(parts, RATE_INPUT), probe(browser, body), "the rate box")


def test_the_rate_label_sheet_reaches_the_drawn_label(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_matrix(browser, payload)
    sheet_agrees(
        only(parts, RATE_LABEL),
        probe(browser, payload["styles"]["rate_label"]),
        "the rate label",
    )


def test_rewriting_the_list_colour_moves_only_the_list_background(browser: Browser):
    """A rewritten list_surface moves the list background and nothing beside it."""
    payload = state_payload(FULL_STATE)
    before = draw_matrix(browser, payload)
    changed = state_payload(FULL_STATE)
    changed["styles"]["list"] = changed["styles"]["list"].replace(
        payload["colors"]["list_surface"], payload["colors"]["input_surface"]
    )
    after = draw_matrix(browser, changed)
    grown = one_in_column(after, SOURCE_LIST, qrs.SOURCE_COLUMN)["style"][
        "backgroundColor"
    ]
    assert (
        grown
        != one_in_column(before, SOURCE_LIST, qrs.SOURCE_COLUMN)["style"][
            "backgroundColor"
        ]
    )
    assert grown == only(after, RATE_INPUT)["style"]["backgroundColor"]
    assert (
        only(after, RATE_LABEL)["style"]["color"]
        == only(before, RATE_LABEL)["style"]["color"]
    ), "the rate label followed a colour it does not carry"


#: MEASURED_LAYOUT_NAMES is the count read off this host, not one assumed.
MEASURED_LAYOUT_NAMES = 10


def test_the_outer_layout_writes_the_property_count_measured_on_this_host(
    browser: Browser,
):
    draw_matrix(browser, state_payload(FULL_STATE))
    written = browser.parsed(
        "Object.keys(acervatorQuickRouting.outerStyle("
        "  acervatorQuickRouting.payload()))"
    )
    assert (
        len(written) == MEASURED_LAYOUT_NAMES
    ), f"the outer layout writes {len(written)} properties on this host: {written}"


def test_a_two_hundred_character_name_does_not_widen_the_list(browser: Browser):
    """A CSS box grows to fit where Qt clips, so the list must clip too."""
    payload = payload_for(
        {"tab": {"widget_symbols": {ALPHA: LONG_NAME}}, "steps": rebuild([ALPHA])}
    )
    parts = draw_matrix(browser, payload)
    listing = one_in_column(parts, SOURCE_LIST, qrs.SOURCE_COLUMN)
    assert listing["width"] <= int(
        HOST_WIDTH_CSS.rstrip("px")
    ), f"a 200-character name stretched the list to {listing['width']}px"
    label = one_in_column(parts, ROW_LABEL, qrs.SOURCE_COLUMN)
    assert label["style"]["overflowX"] == "hidden"
    assert label["style"]["whiteSpace"] == "nowrap"


def test_a_row_label_carrying_a_tag_draws_as_characters_and_loads_nothing(
    browser: Browser,
):
    """Qt measured this tag as a 16px image; the page must draw the words."""
    browser.js(WATCH_VIOLATIONS)
    payload = payload_for(
        {"tab": {"widget_symbols": {ALPHA: MARKUP_TEXT}}, "steps": rebuild([ALPHA])}
    )
    parts = draw_matrix(browser, payload)
    browser.settle(SETTLE_MS)
    label = one_in_column(parts, ROW_LABEL, qrs.SOURCE_COLUMN)
    assert MARKUP_TEXT in label["text"], f"the tag was not drawn as words: {label}"
    assert "<img" not in label["html"], f"the page built a tag: {label['html']}"
    assert browser.js("document.images.length") == 0
    assert browser.parsed("window.VIOLATIONS") == []


def test_a_refusal_carrying_a_tag_draws_as_characters_and_loads_nothing(
    browser: Browser,
):
    """The Qt message box renders this tag; the page must not."""
    browser.js(WATCH_VIOLATIONS)
    payload = payload_for(
        {
            "tab": {"widget_symbols": SYMBOLS},
            "rate": MARKUP_TEXT,
            "steps": rebuild() + [CONNECT],
            STEP_SOURCES: [ALPHA],
            STEP_DESTS: [BETA],
        }
    )
    parts = draw_matrix(browser, payload)
    browser.settle(SETTLE_MS)
    notices = at_path(parts, MATRIX + "/notices/notice")
    assert notices, "the panel refused the click but drew no message"
    assert any(MARKUP_TEXT in one["text"] for one in notices), notices
    assert browser.js("document.images.length") == 0
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_image_check_would_see_an_image_the_page_built(browser: Browser):
    draw_matrix(browser, state_payload(FULL_STATE))
    assert browser.js("document.images.length") == 0
    browser.js("document.body.appendChild(document.createElement('img'));")
    assert browser.js("document.images.length") == 1


def press(browser: Browser, key: str) -> list:
    browser.js(
        'window.HOST.querySelector(\'[data-part="action-button"]'
        "[data-key=" + json.dumps(key) + "]').click();"
    )
    return browser.parsed("acervatorQuickRouting.sent()")


@pytest.mark.parametrize("at, key", list(enumerate(qrs.BUTTON_KEYS)))
def test_each_button_sends_its_own_action_and_its_own_step(
    browser: Browser, at: int, key: str
):
    payload = state_payload("ticked")
    draw_matrix(browser, payload)
    assert browser.parsed("acervatorQuickRouting.sent()") == []
    sent = press(browser, key)
    assert len(sent) == 1, f"{key} sent {sent}"
    assert sent[0]["action"] == qrs.ACTION_ORDER[at]
    assert sent[0]["params"][qrs.STEPS_PARAM] == [key]
    assert sent[0]["params"][STEP_SOURCES] == payload["selected"]["sources"]
    assert sent[0]["params"][STEP_DESTS] == payload["selected"]["destinations"]


def test_a_button_carries_the_rate_that_was_typed_into_the_box(browser: Browser):
    draw_matrix(browser, state_payload("ticked"))
    browser.js(
        "(function () {"
        "  var box = window.HOST.querySelector('[data-part=\"rate-input\"]');"
        "  var setter = Object.getOwnPropertyDescriptor("
        "    window.HTMLInputElement.prototype, 'value').set;"
        "  setter.call(box, '40');"
        "  box.dispatchEvent(new Event('input', { bubbles: true })); })()"
    )
    sent = browser.parsed("acervatorQuickRouting.sent()")
    assert sent and sent[-1]["params"][qrs.RATE_PARAM] == "40", sent
    pressed = press(browser, qrs.CONNECT_STEP)
    assert pressed[-1]["params"][qrs.RATE_PARAM] == "40", pressed


def test_a_row_tick_carries_the_bot_it_names_and_both_columns(browser: Browser):
    draw_matrix(browser, state_payload("scoped"))
    browser.js(
        'window.HOST.querySelector(\'[data-part="list-row"]'
        "[data-column=" + json.dumps(qrs.SOURCE_COLUMN) + "]"
        "[data-key=" + json.dumps(GAMMA) + "] "
        '[data-part="row-check"]\').click();'
    )
    sent = browser.parsed("acervatorQuickRouting.sent()")
    assert sent, "ticking a row sent nothing"
    assert sent[-1]["action"] == STEP_SOURCES
    assert sent[-1]["params"][STEP_SOURCES] == [GAMMA]
    assert sent[-1]["params"][STEP_DESTS] == []


#: SUB_PIXEL allows the fraction a device pixel offset lands off by.
SUB_PIXEL = 1

SOURCE_LIST_NODE = (
    'window.HOST.querySelector(\'[data-part="bot-list"]'
    "[data-column=" + json.dumps(qrs.SOURCE_COLUMN) + "]')"
)


def scroll_range(browser: Browser) -> list:
    """The offset the source list took, and the furthest it could take."""
    return browser.parsed(
        "(function () { var el = "
        + SOURCE_LIST_NODE
        + "; return [el.scrollTop, el.scrollHeight - el.clientHeight]; })()"
    )


def test_a_short_list_clamps_the_saved_offset_the_way_the_scrollbar_does(
    browser: Browser,
):
    payload = state_payload("scrolled")
    parts = draw_matrix(browser, payload)
    listing = one_in_column(parts, SOURCE_LIST, qrs.SOURCE_COLUMN)
    assert listing["attrs"]["data-scroll"] == str(payload["scroll"]["source"])
    taken, furthest = scroll_range(browser)
    assert taken == min(payload["scroll"]["source"], furthest), (taken, furthest)


def test_a_long_list_takes_the_saved_offset_whole(browser: Browser):
    """A short list clamps to zero, so a long one proves scroll_range lands."""
    many = ["bot-" + str(one) for one in range(40)]
    payload = payload_for(
        {
            "tab": {"widget_symbols": SYMBOLS},
            "source_scroll": 35,
            "steps": rebuild(many) + rebuild(many),
        }
    )
    draw_matrix(browser, payload)
    taken, furthest = scroll_range(browser)
    assert furthest > payload["scroll"]["source"], f"nothing to scroll: {furthest}"
    assert abs(taken - payload["scroll"]["source"]) <= SUB_PIXEL, (taken, furthest)


def test_a_row_keeps_its_own_height_when_the_list_holds_more_than_it_shows(
    browser: Browser,
):
    """A flex column squashed every row to 7px before the row was told not to."""
    many = ["bot-" + str(one) for one in range(40)]
    payload = payload_for({"tab": {"widget_symbols": SYMBOLS}, "steps": rebuild(many)})
    parts = draw_matrix(browser, payload)
    rows = in_column(parts, ROWS, qrs.SOURCE_COLUMN)
    assert len(rows) == len(many)
    labels = in_column(parts, ROW_LABEL, qrs.SOURCE_COLUMN)
    short = [one for one, other in zip(rows, labels) if one["height"] < other["height"]]
    assert not short, f"{len(short)} rows are shorter than their own label"


def test_every_button_the_surface_names_is_drawn_once(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_matrix(browser, payload)
    drawn = [one["attrs"]["data-key"] for one in at_path(parts, BUTTONS)]
    assert drawn == payload["wiring"]["button_keys"]
    for key in drawn:
        one = named(parts, BUTTONS, key)
        assert one["text"] == payload["texts"][key]
        assert one["attrs"]["title"] == payload["tooltips"][key]


def test_every_row_the_surface_sent_is_drawn_under_its_own_name(browser: Browser):
    payload = payload_for(
        {"tab": {"widget_symbols": SYMBOLS}, "steps": rebuild(NUMERIC_NAMES)}
    )
    parts = draw_matrix(browser, payload)
    drawn = [
        one["attrs"]["data-key"]
        for one in at_path(parts, ROWS)
        if one["attrs"]["data-column"] == qrs.SOURCE_COLUMN
    ]
    assert drawn == NUMERIC_NAMES, f"the drawn order is {drawn}"


def test_the_page_loads_the_module_after_the_modules_it_reads():
    lines = INDEX_HTML.read_text(encoding="utf-8").splitlines()
    order = [one.strip() for one in lines if "src=" in one]

    def at(name: str) -> int:
        for index, one in enumerate(order):
            if name in one:
                return index
        raise AssertionError(f"{name} is on no script line of {INDEX_HTML.name}")

    mine = at(MODULE_PATH.name)
    for name in ("react.production", "design_tokens.js", "shared_widgets.js"):
        assert at(name) < mine, f"{name} loads after {MODULE_PATH.name}"
    assert at(HEADER_PATH.name) < mine
