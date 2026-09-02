"""The React Live Bot Settings window, driven with pytest against its
surface."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import bot_live_settings_surface as bls
from src.gui.main_tabs import design_system_surface as dss
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    new_engine,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "bot_live_settings.js"
TOKENS_PATH = WEB / "design_tokens.js"
WIDGETS_PATH = WEB / "shared_widgets.js"
HEADER_PATH = WEB / "header_strip.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: One lock for the whole run, so no worker reads a swapped module.
LOCK_PATH = Path(tempfile.gettempdir()) / "acervator_bot_live_settings_swap.lock"
LOCK_ATTEMPTS = 400_000


@contextlib.contextmanager
def module_held(attempts: int = LOCK_ATTEMPTS):
    """Takes LOCK_PATH so one worker at a time swaps bot_live_settings.js."""
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

#: Wide enough that a never-shown window does not read every width as zero.
HOST_WIDTH_CSS = "900px"
HOST_HEIGHT_CSS = "800px"

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

BOT_ID = "botalpha0001beta"
OTHER_ID = "botbravo0002beta"
THIRD_ID = "botcharlie003bet"
SYMBOL = "BTC/USD"

MARKUP_TEXT = '<img src="file:///c:/windows/win.ini">'
LONG_NAME = "N" * 200
NEWLINE_NAME = "two\nlines"

#: The three tabs, per widget kind, this shell draws its own words into.
SHELL_WIDGETS = {
    "QLabel": ("header_label", "state_label", "change_label"),
    "QPushButton": ("prev_label", "next_label", "apply_label", "close_label"),
    "QTabBar": ("tab_status", "tab_settings"),
}


def bot(**over: Any) -> dict:
    """One invented bot record in the shape the bridge handler reads."""
    found = {
        "symbol": SYMBOL,
        "mode": bls.MODE_SCRUMMING,
        "state": bls.STATE_RUNNING,
        "bot_id": BOT_ID,
        "fields": {"target_balance": 10.0, "visibility": True},
    }
    found.update(over)
    return found


SWARM = [OTHER_ID, BOT_ID, THIRD_ID]

#: STATES holds every state of the window the bridge can be driven into.
STATES = {
    "unbuilt": [{}],
    "alone": [{"bot": bot()}],
    "swarm": [{"bot": bot(), "siblings": SWARM}],
    "extractor": [{"bot": bot(mode=bls.MODE_EXTRACTOR)}],
    "idle": [{"bot": bot(state=bls.STATE_IDLE)}],
    "paused": [{"bot": bot(state=bls.STATE_PAUSED)}],
    "error": [{"bot": bot(state=bls.STATE_ERROR)}],
    "stopped": [{"bot": bot(state=bls.STATE_STOPPED)}],
    "cooldown": [{"bot": bot(state=bls.STATE_COOLDOWN)}],
    "unknown_state": [{"bot": bot(state="weird")}],
    "pending": [{"bot": bot()}, {"mark": {"target_balance": 25.0}}],
    "two_pending": [
        {"bot": bot()},
        {"mark": {"target_balance": 25.0, "visibility": False}},
    ],
    "reverted": [{"bot": bot()}, {"mark": {"target_balance": 10.0}}],
    "applied": [{"bot": bot()}, {"mark": {"target_balance": 25.0}}, {"apply": True}],
    "navigated": [{"bot": bot(), "siblings": SWARM}, {"navigate": bls.NEXT_STEP}],
    "nav_refused": [{"bot": bot()}, {"navigate": bls.PREV_STEP}],
}
STATE_NAMES = tuple(STATES)
FULL_STATE = "swarm"
BUILT_STATES = tuple(name for name in STATE_NAMES if name != "unbuilt")


def encoded(found: dict) -> dict:
    """One payload after the round trip through JSON the bridge makes."""
    return json.loads(json.dumps(found, ensure_ascii=True))


def payload_for(steps: list) -> dict:
    bls.view_model({"reset": True})
    found: dict = {}
    for one in steps:
        found = bls.view_model(dict(one))
    return encoded(found)


def state_payload(name: str) -> dict:
    return payload_for(STATES[name])


def routed_payload(**wiring: Any) -> dict:
    """One window built straight off a bot the bridge handler cannot make."""
    source = bls.BotSource(
        config=bls.BotConfigSource(fields={"target_balance": 10.0}), **wiring
    )
    model = bls.build_model(bot=source, build_now=True)
    model.mark_changed("target_balance", 25.0)
    model.apply_changes()
    return encoded(bls.build_view_model(model))


def token_payload() -> dict:
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


class JsRuntime(JsEngine):
    """A QJSEngine holding the window module and a ``window`` global."""

    module_path = MODULE_PATH
    setter = "acervatorSetBotLiveSettings"

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
        return self.json("acervatorBotLiveSettings." + answerer + "(JSON.parse(NAME))")

    def field(self, name: str) -> Any:
        return self.named("field", name)

    def answer(self, expression: str) -> Any:
        return self.json("acervatorBotLiveSettings." + expression)


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
    declared = js.answer("declaredNames()")
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
    declared = js.answer("declaredNames()")
    assert sorted(set(payload) - set(declared)) == ["only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_declares(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload.pop("prev_tooltip")
    js.push(payload)
    declared = js.answer("declaredNames()")
    assert sorted(set(declared) - set(payload)) == ["prev_tooltip"]


def test_the_field_value_check_names_one_changed_field(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["apply_label"] = payload["apply_label"] + "!"
    js.push(payload)
    shipped = state_payload(FULL_STATE)
    differing = sorted(name for name in shipped if js.field(name) != shipped[name])
    assert differing == ["apply_label"], f"the check named {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(js: JsRuntime, state):
    payload = state_payload(state)
    report = js.push(payload)
    assert report["declared"]["fields"] == len(payload)
    assert report["held"]["fields"] == len(payload)
    assert report["declared"]["tabs"] == len(payload["tabs"])
    assert report["held"]["tabs"] == len(payload["tabs"])
    assert report["declared"]["shortcuts"] == len(payload["shortcuts"])
    assert report["held"]["shortcuts"] == len(payload["shortcuts"])
    assert report["declared"]["changes"] == len(payload["changes"])
    assert report["held"]["changes"] == len(payload["changes"])
    assert report["declared"]["spaces"] == report["held"]["spaces"]
    assert report["held"]["spaces"] == len(bls.TAB_PLAN)


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    whole = len(payload)
    del payload["prev_tooltip"]
    report = js.push(payload)
    assert report["declared"]["fields"] == whole
    assert report["held"]["fields"] == whole - 1
    named = [one for one in report["faults"] if one["field"] == "prev_tooltip"]
    assert named and named[0]["fault"] == "missing", report["faults"]


def test_a_tab_the_module_keeps_no_space_for_shortens_only_the_held_tab_count(
    js: JsRuntime,
):
    payload = state_payload(FULL_STATE)
    payload["tabs"] = payload["tabs"] + ["Invented"]
    report = js.push(payload)
    assert report["declared"]["tabs"] == report["held"]["tabs"] + 1
    named = [one for one in report["faults"] if one["fault"] == "unplaced"]
    assert named and named[0]["detail"] == "Invented", report["faults"]


def test_an_edit_left_out_of_the_change_line_shortens_only_the_held_count(
    js: JsRuntime,
):
    payload = state_payload("two_pending")
    payload["change_label"] = bls.pending_text(["target_balance"])
    report = js.push(payload)
    assert report["declared"]["changes"] == report["held"]["changes"] + 1


def test_a_shortcut_pair_with_no_step_shortens_only_the_held_count(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["shortcuts"][0] = []
    report = js.push(payload)
    assert report["declared"]["shortcuts"] == report["held"]["shortcuts"] + 1


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
    walk_payload(
        routed_payload(routes={"set_target_balance_live": {"applied": True}}),
        keys,
        values,
    )
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
PAINTED_VALUES = PUBLISHED_VALUES - AMBIGUOUS - {bls.METHOD}
TOKEN_VALUES = token_values()


def test_no_number_is_written_in_the_module():
    assert not MODULE_LITERALS[
        "numbers"
    ], f"bot_live_settings.js holds numeric literals: {MODULE_LITERALS['numbers']}"


def test_no_colour_is_written_in_the_module():
    found = sorted(one for one in MODULE_LITERALS["strings"] if HEX_COLOUR.search(one))
    assert not found, f"bot_live_settings.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_window_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & PAINTED_VALUES)
    assert not written, f"bot_live_settings.js writes window values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"bot_live_settings.js writes token values: {written}"


def test_no_slash_stands_outside_a_comment_in_the_module():
    assert not MODULE_LITERALS["slashes"], (
        "bot_live_settings.js holds a slash outside a comment, which the scan "
        f"cannot read: {MODULE_LITERALS['slashes']}"
    )


WRITINGS = {
    "number": "var written = 12;",
    "colour": 'var written = "' + dss.TEXT_MED + '";',
    "painted": 'var written = "' + bls.APPLY_LABEL + '";',
    "slash": "var written = 8 " + chr(47) + " 2;",
}


@pytest.mark.parametrize("kind", sorted(WRITINGS))
def test_the_literal_scan_reports_one_value_written_into_the_real_module(kind: str):
    """One value at a time goes into the shipped module and must be caught."""
    with module_held():
        original = MODULE_PATH.read_bytes()
        before = hashlib.sha256(original).hexdigest()
        try:
            swap_module(MODULE_PATH, original + b"\n" + WRITINGS[kind].encode("utf-8"))
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
    mine = js.answer("kinds()")
    missing = sorted(set(theirs) - set(mine))
    assert not missing, f"{state}: the module reads no type at {missing[:6]}"
    extra = sorted(set(mine) - set(theirs))
    assert not extra, f"{state}: the module invented paths {extra[:6]}"
    differing = sorted(one for one in theirs if theirs[one] != mine[one])
    assert not differing, f"{state}: types differ at {differing[:6]}"


def test_the_type_check_names_one_changed_type(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["minimum_w_px"] = "640"
    js.push(payload)
    assert js.answer("kinds()")["minimum_w_px"] == "string"


def test_the_type_walk_names_a_null_inside_a_list(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["siblings"] = [None]
    js.push(payload)
    assert js.answer("kinds()")["siblings.0"] == "null"


def test_the_type_walk_names_a_scalar_where_a_bag_belongs(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["timers"] = 7
    js.push(payload)
    assert js.answer("kinds()")["timers"] == "number"


@pytest.mark.parametrize("name", ["actions", "changes", "state_colors", "timers"])
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


@pytest.mark.parametrize("name", ["calls", "shortcuts", "tab_plan", "tabs"])
def test_a_scalar_where_a_list_belongs_is_named(js: JsRuntime, name: str):
    """A scalar slips past a member walk, so its own field is named."""
    payload = state_payload(FULL_STATE)
    payload[name] = 7
    report = js.push(payload)
    named = [
        one
        for one in report["faults"]
        if one["fault"] == "not-a-list" and one["field"] == name
    ]
    assert named and named[0]["detail"] == "number", report["faults"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_shape_check_is_quiet_on_a_shipped_payload(js: JsRuntime, state: str):
    report = js.push(state_payload(state))
    named = [
        one
        for one in report["faults"]
        if one["fault"] in ("not-a-list", "not-an-object", "not-plain")
    ]
    assert named == [], f"{state}: a shipped shape was refused: {named}"


@pytest.mark.parametrize("state", BUILT_STATES)
def test_the_tab_order_is_the_order_the_surface_sent(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    assert js.answer("tabNames()") == payload["tabs"]


def test_each_tab_reaches_the_space_its_own_unit_fills(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    js.push(payload)
    for name in payload["tabs"]:
        page = js.named("pageOf", name)
        assert page is not None, f"{name} reaches no space"
        assert page["part"] in js.answer("emptySpaces()")
        assert page["fills"].endswith("_surface"), page


def test_a_reordered_tab_list_is_read_in_its_new_order_and_named(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["tabs"] = list(reversed(payload["tabs"]))
    report = js.push(payload)
    assert js.answer("tabNames()") == payload["tabs"]
    named = [one for one in report["faults"] if one["fault"] == "disagrees"]
    assert named, "a tab list out of plan order was not named"


#: NUMERIC_FIELDS are edited field names a JavaScript object reorders as keys.
NUMERIC_FIELDS = ["7", "3", "1"]


def numeric_payload() -> dict:
    steps: list = [{"bot": bot()}]
    steps.extend({"mark": {name: True}} for name in NUMERIC_FIELDS)
    return payload_for(steps)


def test_the_edited_field_order_is_the_order_the_change_line_draws(js: JsRuntime):
    js.push(numeric_payload())
    assert js.answer("editedFields()") == NUMERIC_FIELDS


def test_reading_the_edited_fields_off_the_bag_loses_the_order(js: JsRuntime):
    """The bag walk is what #276 breaks, so the line beside it must be read."""
    js.push(numeric_payload())
    keys = js.json("Object.keys(acervatorBotLiveSettings.bag('changes'))")
    assert keys != NUMERIC_FIELDS, "the bag kept the order, so this proves nothing"
    assert sorted(keys) == sorted(NUMERIC_FIELDS)


def test_a_bag_whose_order_the_change_line_disagrees_with_is_named(js: JsRuntime):
    report = js.push(numeric_payload())
    named = [one for one in report["faults"] if one["field"] == "changes"]
    assert named and named[0]["fault"] == "disagrees", report["faults"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_order_check_is_quiet_where_no_field_name_is_numeric(
    js: JsRuntime, state: str
):
    report = js.push(state_payload(state))
    named = [one for one in report["faults"] if one["field"] == "changes"]
    assert named == [], f"{state}: a shipped change bag was refused: {named}"


def test_every_bag_the_payload_carries_is_keyed_by_a_name_the_surface_owns(
    js: JsRuntime,
):
    """A bag keyed by an edited field is the shape #276 reorders."""
    payload = numeric_payload()
    js.push(payload)
    sent = set(NUMERIC_FIELDS)
    reordering = []
    for name in js.answer("bagNames()"):
        keys = js.json("Object.keys(acervatorBotLiveSettings.bag('" + name + "'))")
        if set(keys) & sent:
            reordering.append(name)
    assert reordering == ["changes"], f"these bags carry an edited name: {reordering}"


#: EIGHT_DIGIT names each shipped sheet field against its refused properties.
EIGHT_DIGIT = {
    "state_style": ["background"],
    "nav_style": ["border", "background"],
}


@pytest.mark.parametrize("state", ("alone", "paused", "error", "cooldown"))
def test_the_shipped_state_badge_fill_is_refused_as_a_qt_colour(
    js: JsRuntime, state: str
):
    """#266: `#ffaa0022` is amber at 13% in CSS and opaque `#aa0022` in Qt."""
    report = js.push(state_payload(state))
    named = [
        one
        for one in report["faults"]
        if one["fault"] == "qt-colour" and one["field"] == "state_style"
    ]
    assert named, f"{state}: the eight-digit badge fill was not refused"
    assert named[0]["detail"] == "AARRGGBB"
    assert named[0]["where"] == "background"


@pytest.mark.parametrize("state", ("idle", "stopped", "unknown_state"))
def test_a_three_digit_state_colour_is_left_alone(js: JsRuntime, state: str):
    """A five-digit fill is invalid in Qt and in CSS alike, so both drop it."""
    payload = state_payload(state)
    report = js.push(payload)
    named = [
        one
        for one in report["faults"]
        if one["fault"] == "qt-colour" and one["field"] == "state_style"
    ]
    assert named == [], f"{state}: a five-digit fill was named eight-digit: {named}"
    assert "#" in payload["state_style"]


def test_the_navigation_button_border_is_refused_as_a_qt_colour(js: JsRuntime):
    """#266: `#00ffcc55` is a faint edge in CSS and fully transparent in Qt."""
    report = js.push(state_payload(FULL_STATE))
    named = [
        one
        for one in report["faults"]
        if one["fault"] == "qt-colour" and one["field"] == "nav_style"
    ]
    assert len(named) == 2, f"the nav sheet named {named}"
    assert sorted(one["where"] for one in named) == ["QPushButton:hover", "border"]


QUIET_SHEETS = ["apply_style", "change_style", "close_style", "header_style"]


@pytest.mark.parametrize("field", QUIET_SHEETS)
def test_no_other_sheet_this_window_paints_carries_a_swapped_colour(
    js: JsRuntime, field: str
):
    report = js.push(state_payload(FULL_STATE))
    named = [
        one
        for one in report["faults"]
        if one["fault"] == "qt-colour" and one["field"] == field
    ]
    assert named == [], f"{field} was refused: {named}"


def test_the_colour_refusal_names_a_byte_alpha(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["change_style"] = "background:rgba(1,2,3,128);"
    report = js.push(payload)
    named = [
        one
        for one in report["faults"]
        if one["fault"] == "qt-colour" and one["field"] == "change_style"
    ]
    assert named and named[0]["detail"] == "rgba(", report["faults"]


def test_a_refused_colour_is_left_out_of_the_style_the_module_paints(js: JsRuntime):
    kept = js.named("keptSheet", "color:#80ff00cc;background:#101010;")
    assert "#80ff00cc" not in kept
    assert "#101010" in kept


def test_the_alpha_scale_is_published_and_a_byte_reads_back_as_a_fraction(
    js: JsRuntime,
):
    """Alpha arrives as a whole byte; CSS wants the fraction of that scale."""
    assert js.answer("alphaScale()") == 255
    assert js.answer("alphaFraction(255)") == 1.0
    assert js.answer("alphaFraction(0)") == 0.0
    assert js.named("alphaOf", "#00ff8822") == pytest.approx(34 / 255)


def test_the_alpha_answer_is_absent_where_no_eight_digit_colour_stands(js: JsRuntime):
    """A six-digit value carries no alpha, so the fraction above means one."""
    assert js.named("alphaOf", "#00ff88") is None


def test_a_badge_fill_naming_another_state_is_named(js: JsRuntime):
    payload = state_payload("alone")
    payload["state_style"] = payload["state_style"].replace("#00ff8822", "#ff336622")
    report = js.push(payload)
    named = [
        one
        for one in report["faults"]
        if one["fault"] == "disagrees" and one["where"] == "state-badge"
    ]
    assert named and named[0]["field"] == "background", report["faults"]


@pytest.mark.parametrize("state", BUILT_STATES)
def test_the_badge_check_is_quiet_where_the_fill_names_the_drawn_state(
    js: JsRuntime, state: str
):
    report = js.push(state_payload(state))
    named = [one for one in report["faults"] if one["where"] == "state-badge"]
    assert named == [], f"{state}: a shipped badge was refused: {named}"


@pytest.mark.parametrize("name", sorted(sum(SHELL_WIDGETS.values(), ())))
def test_a_word_the_shell_draws_carrying_a_tag_is_named(js: JsRuntime, name: str):
    payload = state_payload(FULL_STATE)
    if name.startswith("tab_"):
        payload["tabs"] = [MARKUP_TEXT] + payload["tabs"]
        payload["tab_plan"] = [[MARKUP_TEXT, "", True, "window"]] + payload["tab_plan"]
        payload[name] = MARKUP_TEXT
    else:
        payload[name] = MARKUP_TEXT
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "markup"]
    assert named, f"{name} carrying a tag was not named: {report['faults']}"


def test_a_symbol_from_stored_state_carrying_a_tag_is_named(js: JsRuntime):
    """The pair reaches the header from the bot's own stored config."""
    payload = payload_for([{"bot": bot(symbol=MARKUP_TEXT)}])
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "markup"]
    assert sorted(one["field"] for one in named) == ["header_label", "title"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_markup_check_is_quiet_on_a_shipped_payload(js: JsRuntime, state: str):
    report = js.push(state_payload(state))
    named = [one for one in report["faults"] if one["fault"] == "markup"]
    assert named == [], f"{state}: shipped text was named as markup: {named}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_shipped_payload_raises_no_fault_beyond_the_two_named_sheets(
    js: JsRuntime, state: str
):
    """Every shipped fault is one of the two #266 colours, and no other."""
    report = js.push(state_payload(state))
    other = [one for one in report["faults"] if one["fault"] != "qt-colour"]
    assert other == [], f"{state}: {len(other)} unexpected faults: {other}"
    for one in report["faults"]:
        assert one["field"] in EIGHT_DIGIT, one
        assert one["detail"] == "AARRGGBB", one


def test_a_window_showing_navigation_with_one_bot_is_named(js: JsRuntime):
    payload = state_payload("alone")
    payload["nav_shown"] = True
    report = js.push(payload)
    named = [one for one in report["faults"] if one["field"] == "nav_shown"]
    assert named and named[0]["fault"] == "disagrees", report["faults"]


def test_a_shortcut_wired_where_navigation_is_hidden_is_named(js: JsRuntime):
    payload = state_payload("alone")
    payload["shortcuts"] = payload["shortcut_plan"]
    report = js.push(payload)
    named = [one for one in report["faults"] if one["field"] == "shortcuts"]
    assert named and named[0]["fault"] == "disagrees", report["faults"]


def test_a_change_line_that_names_no_edited_field_is_named(js: JsRuntime):
    payload = state_payload("pending")
    payload["change_label"] = payload["change_empty_text"]
    report = js.push(payload)
    named = [one for one in report["faults"] if one["field"] == "change_label"]
    assert named and named[0]["fault"] == "disagrees", report["faults"]


def test_an_apply_button_left_live_with_no_edit_is_named(js: JsRuntime):
    payload = state_payload("alone")
    payload["apply_enabled"] = True
    report = js.push(payload)
    named = [one for one in report["faults"] if one["field"] == "apply_enabled"]
    assert named and named[0]["fault"] == "disagrees", report["faults"]


def test_an_applied_line_painted_in_the_pending_colour_is_named(js: JsRuntime):
    payload = state_payload("applied")
    payload["change_style"] = payload["change_pending_style"]
    report = js.push(payload)
    named = [one for one in report["faults"] if one["field"] == "change_style"]
    assert named and named[0]["fault"] == "disagrees", report["faults"]


def test_a_window_opening_below_its_own_floor_is_named(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["opened_size_px"] = [payload["minimum_w_px"] - 1, payload["minimum_h_px"]]
    report = js.push(payload)
    named = [one for one in report["faults"] if one["field"] == "opened_size_px"]
    assert named and named[0]["fault"] == "disagrees", report["faults"]


def test_a_tab_wrapped_against_the_plan_is_named(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["wrapped_tabs"] = payload["wrapped_tabs"][:-1]
    report = js.push(payload)
    named = [one for one in report["faults"] if one["field"] == "wrapped_tabs"]
    assert named and named[0]["fault"] == "disagrees", report["faults"]


def test_a_scroller_asked_for_the_wrong_frame_is_named(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["wrapped_tabs"][0] = [payload["wrapped_tabs"][0][0], True, "Box"]
    report = js.push(payload)
    named = [one for one in report["faults"] if one["field"] == "wrapped_tabs"]
    assert named and named[0]["fault"] == "wrong-type", report["faults"]


def test_a_form_sized_against_the_published_rows_is_named(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    js.push(payload)
    spec = dict(js.answer("formOf()"))
    spec["vertical_spacing_px"] = spec["vertical_spacing_px"] + 1
    payload["forms"] = [spec]
    report = js.push(payload)
    named = [one for one in report["faults"] if one["field"] == "vertical_spacing_px"]
    assert named and named[0]["fault"] == "disagrees", report["faults"]


def test_the_form_settings_the_child_tabs_share_reach_the_module(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    js.push(payload)
    assert js.answer("formOf()") == {
        "field_growth": payload["form_field_growth"],
        "row_wrap": payload["form_row_wrap"],
        "horizontal_spacing_px": payload["form_horizontal_spacing_px"],
        "vertical_spacing_px": payload["form_vertical_spacing_px"],
        "margins_px": payload["form_margins_px"],
    }


def test_an_edit_sent_under_no_bot_id_is_named(js: JsRuntime):
    payload = state_payload("applied")
    payload["sent"][0][0] = 7
    report = js.push(payload)
    named = [one for one in report["faults"] if one["field"] == "sent"]
    assert named and named[0]["fault"] == "wrong-type", report["faults"]


def test_a_payload_that_is_not_an_object_is_named(js: JsRuntime):
    report = js.json("acervatorSetBotLiveSettings(7)")
    assert report["declared"] is None
    assert report["faults"][0]["fault"] == "not-an-object"


def test_the_hostile_check_would_see_a_module_that_raised(js: JsRuntime):
    """A raise inside the module reaches js.json as an error, not a pass."""
    result = js.json(
        "(function () { try { return null.x; } catch (e) { return 1; } })()"
    )
    assert result == 1


def leaves(node: Any, prefix: str = "") -> list:
    """Every value in a payload that is not a bag or a list, by path."""
    if isinstance(node, dict):
        found: list = []
        for key, value in node.items():
            found.extend(leaves(value, f"{prefix}.{key}" if prefix else str(key)))
        return found
    if isinstance(node, list):
        found = []
        for at, one in enumerate(node):
            found.extend(leaves(one, f"{prefix}.{at}"))
        return found
    return [(prefix, node)]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_surface_publishes_data_and_never_a_live_object(state: str):
    """A live object makes the whole reply unencodable the moment it is wired."""
    payload = payload_for(STATES[state])
    json.dumps(payload, ensure_ascii=True)
    wrong = [
        (path, type(value).__name__)
        for path, value in leaves(payload)
        if value is not None and not isinstance(value, (str, int, float, bool))
    ]
    assert not wrong, f"{state}: the payload carries live objects: {wrong}"


def test_the_plain_data_walk_names_a_live_object_the_payload_carries():
    """The walk above passes anything, so one live object must be named."""
    payload = payload_for(STATES["alone"])
    payload["fold_sort_key"] = object()
    wrong = [
        path
        for path, value in leaves(payload)
        if value is not None and not isinstance(value, (str, int, float, bool))
    ]
    assert wrong == ["fold_sort_key"]


def test_the_module_names_a_value_that_is_not_plain_data(js: JsRuntime):
    js.push(state_payload(FULL_STATE))
    assert js.answer("plainness()") == []
    js.run("acervatorBotLiveSettings.payload().skin.live = function () { return 1; };")
    assert js.answer("plainness()") == ["skin.live"]


HOSTILE_FIELDS: dict = {
    "actions_missing": ("actions", None),
    "actions_null": ("actions", None),
    "changes_null": ("changes", None),
    "change_label_number": ("change_label", 7),
    "current_tab_text": ("current_tab", "first"),
    "minimum_size_px_text": ("minimum_size_px", "640x720"),
    "nav_shown_text": ("nav_shown", "yes"),
    "opened_size_px_huge": ("opened_size_px", [10**24, 10**24]),
    "prev_step_text": ("prev_step", "back"),
    "shortcuts_number": ("shortcuts", 7),
    "state_style_null": ("state_style", None),
    "tab_plan_null": ("tab_plan", None),
    "tabs_text": ("tabs", "Status"),
    "title_number": ("title", 7),
}


@pytest.mark.parametrize("case", sorted(HOSTILE_FIELDS))
def test_a_hostile_top_level_field_still_answers(js: JsRuntime, case: str):
    payload = state_payload(FULL_STATE)
    name, value = HOSTILE_FIELDS[case]
    if case.endswith("_missing"):
        del payload[name]
    else:
        payload[name] = value
    report = js.push(payload)
    assert isinstance(report["faults"], list), f"{case} answered no fault list"
    assert report["held"]["fields"] <= report["declared"]["fields"]
    assert js.answer("isLoaded()") is True
    assert isinstance(js.answer("tabNames()"), list)


HOSTILE_SYMBOLS = {
    "nan": float("nan"),
    "inf": float("inf"),
    "minus_inf": float("-inf"),
    "huge": 10**24,
    "number_where_text_belongs": 7,
    "a_newline": NEWLINE_NAME,
    "markup": MARKUP_TEXT,
    "long_name": LONG_NAME,
    "empty": "",
}


@pytest.mark.parametrize("case", sorted(HOSTILE_SYMBOLS))
def test_a_hostile_symbol_still_draws_one_header_and_one_title(js: JsRuntime, case):
    payload = payload_for([{"bot": bot(symbol=HOSTILE_SYMBOLS[case])}])
    report = js.push(payload)
    assert isinstance(report["faults"], list), f"{case} answered no fault list"
    assert isinstance(payload["header_label"], str)
    assert js.field("header_label") == payload["header_label"]
    marked = [one for one in report["faults"] if one["fault"] == "markup"]
    assert bool(marked) is (case == "markup"), report["faults"]


HOSTILE_STATES = {
    "number_where_text_belongs": 7,
    "null": None,
    "markup": MARKUP_TEXT,
    "long_name": LONG_NAME,
    "a_newline": NEWLINE_NAME,
    "empty": "",
    "unknown": "weird",
}


@pytest.mark.parametrize("case", sorted(HOSTILE_STATES))
def test_a_hostile_bot_state_either_draws_a_badge_or_raises_on_the_surface(
    js: JsRuntime, case: str
):
    """A non-string state raises in the surface, exactly as the Qt window does."""
    wanted = HOSTILE_STATES[case]
    if isinstance(wanted, str):
        payload = payload_for([{"bot": bot(state=wanted)}])
        js.push(payload)
        assert js.field("state_label") == payload["state_label"]
        return
    with pytest.raises(AttributeError):
        payload_for([{"bot": bot(state=wanted)}])


def test_a_duplicate_bot_id_in_the_swarm_still_reaches_one_window(js: JsRuntime):
    """A duplicate id is what a bag keyed by bot id collapses to one."""
    payload = payload_for([{"bot": bot(), "siblings": [BOT_ID, BOT_ID, OTHER_ID]}])
    js.push(payload)
    assert js.named("list", "siblings") == [BOT_ID, BOT_ID, OTHER_ID]
    assert payload["nav_shown"] is True


def test_a_bot_the_swarm_does_not_carry_still_steps_to_a_neighbour(js: JsRuntime):
    """The window loses its place, records it, and still steps to the next bot."""
    payload = payload_for(
        [
            {"bot": bot(bot_id="botmissing000000"), "siblings": SWARM},
            {"navigate": bls.NEXT_STEP},
        ]
    )
    report = js.push(payload)
    assert [bls.NAVIGATE_LOST, 0] in payload["calls"]
    assert payload["pending_navigate_to"] == SWARM[1]
    assert payload["accepted"] is True
    assert isinstance(report["faults"], list)


def test_a_mode_no_plan_row_names_leaves_only_the_two_shared_tabs(js: JsRuntime):
    """An unknown mode drops every mode-specific tab and keeps the shared two."""
    payload = payload_for([{"bot": bot(mode="weird")}])
    report = js.push(payload)
    assert payload["tabs"] == [payload["tab_status"], payload["tab_settings"]]
    assert js.answer("tabNames()") == payload["tabs"]
    assert [one for one in report["faults"] if one["fault"] != "qt-colour"] == []


def test_an_edit_the_config_has_no_field_for_is_dropped_and_counted_as_none(
    js: JsRuntime,
):
    payload = payload_for(
        [{"bot": bot()}, {"mark": {"no_such_field": 1}}, {"apply": True}]
    )
    js.push(payload)
    assert [bls.APPLY_DROPPED, "no_such_field"] in payload["calls"]
    assert payload["applied"] == []
    assert payload["change_label"] == bls.applied_text(0)
    assert js.answer("editedFields()") == []


def test_a_swarm_of_one_refuses_the_step_and_draws_no_navigation(js: JsRuntime):
    payload = state_payload("nav_refused")
    js.push(payload)
    assert payload["pending_navigate_to"] is None
    assert payload["nav_shown"] is False
    assert [bls.NAVIGATE_REFUSED, 0] in payload["calls"]


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
                if self.js("typeof window.acervatorSetBotLiveSettings") == "function":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the window module: readyState "
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
    "color",
    "backgroundColor",
    "fontSize",
    "fontWeight",
    "whiteSpace",
    "overflowX",
    "overflowY",
    "textOverflow",
    "minWidth",
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "borderTopStyle",
    "borderTopWidth",
    "borderTopColor",
    "borderTopLeftRadius",
    "borderBottomRightRadius",
    "flexGrow",
    "visibility",
]

#: EXPANDED holds each Qt shorthand against the computed names it settles into.
EXPANDED = {
    "border": ("borderTopStyle", "borderTopWidth", "borderTopColor"),
    "border-radius": ("borderTopLeftRadius", "borderBottomRightRadius"),
    "padding": ("paddingLeft", "paddingTop", "paddingRight", "paddingBottom"),
    "background": ("backgroundColor",),
    "background-color": ("backgroundColor",),
    "font-size": ("fontSize",),
    "font-weight": ("fontWeight",),
    "color": ("color",),
    "min-width": ("minWidth",),
}

WATCH_VIOLATIONS = (
    "window.VIOLATIONS = [];"
    "document.addEventListener('securitypolicyviolation', function (e) {"
    "  window.VIOLATIONS.push(e.violatedDirective + ' ' + e.blockedURI); });"
)

PAGE_HELPERS = (
    "window.HOST = document.getElementById('bot-live-settings-host');"
    "if (window.HOST === null) {"
    "  window.HOST = document.createElement('div');"
    "  window.HOST.id = 'bot-live-settings-host';"
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


def draw_window(browser: Browser, payload: dict) -> list:
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorBotLiveSettings.forget();"
        "acervatorSetBotLiveSettings(JSON.parse(window.PAYLOAD));"
        "acervatorBotLiveSettings.renderWindow(window.HOST);"
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
    for prop, value in python_declarations(body):
        if len(value.partition("#")[2].split()[0] if "#" in value else "") == 8:
            continue
        names.extend(EXPANDED.get(prop, (prop,)))
    if not names:
        return {}
    kept = ";".join(
        f"{prop}:{value}"
        for prop, value in python_declarations(body)
        if len(value.partition("#")[2].split()[0] if "#" in value else "") != 8
    )
    return browser.parsed(
        "window.probeStyle("
        + json.dumps(kept)
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


def sheet_agrees(drawn: dict, expected: dict, where: str) -> None:
    assert expected, f"{where}: the probe took no value, so this compares nothing"
    differing = {
        name: (value, drawn["style"].get(name))
        for name, value in expected.items()
        if drawn["style"].get(name) != value
    }
    assert not differing, f"{where}: wanted against drawn {differing}"


WINDOW = "bot-live-settings"
HEADER = WINDOW + "/header-row"
HEADER_LABEL = HEADER + "/header-label"
STATE_BADGE = HEADER + "/state-badge"
PREV_BUTTON = HEADER + "/prev-button"
NEXT_BUTTON = HEADER + "/next-button"
TAB_BAR = WINDOW + "/tab-bar"
TAB_BUTTON = TAB_BAR + "/tab-button"
TAB_PAGES = WINDOW + "/tab-pages"
FOOTER = WINDOW + "/footer-row"
APPLY_BUTTON = FOOTER + "/apply-button"
CLOSE_BUTTON = FOOTER + "/close-button"
CHANGE_LABEL = WINDOW + "/change-label"


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    assert browser.js("typeof window.acervatorBotLiveSettings") == "object"
    assert browser.js("typeof window.acervatorSetBotLiveSettings") == "function"
    assert browser.js("typeof window.acervatorLoadBotLiveSettings") == "function"
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_module_makes_no_network_call_of_its_own(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    draw_window(browser, state_payload(FULL_STATE))
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


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_drawn_element_carries_a_name(browser: Browser, state: str):
    draw_window(browser, state_payload(state))
    counts = browser.parsed(
        "[window.HOST.querySelectorAll('*').length,"
        " window.HOST.querySelectorAll('[data-part]').length]"
    )
    assert counts[0] == counts[1], f"{state}: {counts[0]} elements, {counts[1]} named"
    assert counts[0] > 0, f"{state}: the window drew nothing at all"


def test_the_name_check_would_see_an_element_with_no_name(browser: Browser):
    draw_window(browser, state_payload(FULL_STATE))
    counts = browser.parsed(
        "(function () {"
        "  window.HOST.firstChild.appendChild(document.createElement('b'));"
        "  return [window.HOST.querySelectorAll('*').length,"
        "    window.HOST.querySelectorAll('[data-part]').length]; })()"
    )
    assert counts[0] == counts[1] + 1


@pytest.mark.parametrize(
    "path, field",
    [
        (HEADER_LABEL, "header_style"),
        (STATE_BADGE, "state_style"),
        (CHANGE_LABEL, "change_style"),
    ],
)
def test_each_label_sheet_reaches_its_drawn_label(
    browser: Browser, path: str, field: str
):
    payload = state_payload("pending")
    parts = draw_window(browser, payload)
    sheet_agrees(only(parts, path), probe(browser, payload[field]), path)


@pytest.mark.parametrize(
    "path, field",
    [
        (PREV_BUTTON, "nav_style"),
        (APPLY_BUTTON, "apply_style"),
        (CLOSE_BUTTON, "close_style"),
    ],
)
def test_each_button_sheet_reaches_its_drawn_button(
    browser: Browser, path: str, field: str
):
    payload = state_payload("pending")
    parts = draw_window(browser, payload)
    body = qt_block(payload[field], "QPushButton")
    sheet_agrees(only(parts, path), probe(browser, body), path)


def test_the_two_labels_take_different_colours(browser: Browser):
    """The header label and the state badge must draw in different colors."""
    parts = draw_window(browser, state_payload("pending"))
    assert (
        only(parts, HEADER_LABEL)["style"]["color"]
        != only(parts, STATE_BADGE)["style"]["color"]
    )


def test_the_apply_button_paints_its_disabled_block_only_when_no_edit_stands(
    browser: Browser,
):
    """A flag beside a colour is the shape that paints every cell one colour."""
    quiet = draw_window(browser, state_payload("alone"))
    live = draw_window(browser, state_payload("pending"))
    body = qt_block(state_payload("alone")["apply_style"], "QPushButton:disabled")
    wanted = probe(browser, body)
    sheet_agrees(only(quiet, APPLY_BUTTON), wanted, "the disabled Apply button")
    differing = [
        name
        for name, value in wanted.items()
        if only(live, APPLY_BUTTON)["style"].get(name) == value
    ]
    assert differing != sorted(wanted), "the live Apply button paints the same"
    assert only(quiet, APPLY_BUTTON)["attrs"]["data-enabled"] == "false"
    assert only(live, APPLY_BUTTON)["attrs"]["data-enabled"] == "true"


def test_the_navigation_buttons_are_hidden_rather_than_removed(browser: Browser):
    """Qt calls setVisible on both, so the pair exists in either state."""
    alone = draw_window(browser, state_payload("alone"))
    swarm = draw_window(browser, state_payload("swarm"))
    for path in (PREV_BUTTON, NEXT_BUTTON):
        assert only(alone, path)["attrs"]["data-visible"] == "false"
        assert "hidden" in only(alone, path)["attrs"], path
        assert only(swarm, path)["attrs"]["data-visible"] == "true"
        assert "hidden" not in only(swarm, path)["attrs"], path


def test_the_navigation_buttons_carry_the_step_the_surface_names(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_window(browser, payload)
    assert only(parts, PREV_BUTTON)["attrs"]["data-step"] == str(payload["prev_step"])
    assert only(parts, NEXT_BUTTON)["attrs"]["data-step"] == str(payload["next_step"])


#: MEASURED_NAV_PROPERTIES is the count read off this host, not one assumed.
MEASURED_NAV_PROPERTIES = 7


def test_the_navigation_sheet_writes_the_property_count_measured_on_this_host(
    browser: Browser,
):
    """One of the eight base declarations is refused, so seven reach the page."""
    draw_window(browser, state_payload(FULL_STATE))
    written = browser.parsed(
        "Object.keys(acervatorBotLiveSettings.styleOf("
        "  acervatorBotLiveSettings.payload().nav_style))"
    )
    assert (
        len(written) == MEASURED_NAV_PROPERTIES
    ), f"the nav sheet writes {len(written)} properties here: {written}"


def test_a_border_is_compared_against_the_whole_declaration_and_not_a_number(
    browser: Browser,
):
    """A one-pixel border computed to 0.8px here, so no typed number would do."""
    payload = state_payload(FULL_STATE)
    parts = draw_window(browser, payload)
    body = qt_block(payload["close_style"], "QPushButton")
    wanted = probe(browser, body)
    assert "borderTopWidth" in wanted, f"the probe took no border: {wanted}"
    assert (
        only(parts, CLOSE_BUTTON)["style"]["borderTopWidth"] == wanted["borderTopWidth"]
    )


#: SCREEN_COLOURS is every colour a sheet on this window paints with.
SCREEN_COLOURS = {
    "PRIMARY": dss.PRIMARY,
    "SUCCESS": dss.SUCCESS,
    "WARNING": dss.WARNING,
    "ERROR": dss.ERROR,
    "SURFACE_CONTROL": dss.SURFACE_CONTROL,
    "SURFACE_CHART": dss.SURFACE_CHART,
    "CARD_METRIC_BORDER": dss.CARD_METRIC_BORDER,
    "MENU_BORDER": dss.MENU_BORDER,
}

#: RESOLVED_COLOURS is the count read off this host, not one assumed.
RESOLVED_COLOURS = 8

#: A colour no design token holds, so the window keeps the value itself.
UNCARRIED_COLOUR = "#0b1d2e"


def named_tokens(browser: Browser, values: dict) -> dict:
    browser.js("window.VALUES = " + json.dumps(json.dumps(values)))
    return browser.parsed(
        "(function () { var found = {}; var sent = JSON.parse(window.VALUES);"
        "  Object.keys(sent).forEach(function (one) {"
        "    var name = acervatorBotLiveSettings.variableFor(sent[one]);"
        "    found[one] = name === undefined ? null : name; });"
        "  return found; })()"
    )


def test_every_colour_this_window_paints_reaches_its_own_token(browser: Browser):
    """A colour paints through a token only where exactly one token holds it."""
    draw_window(browser, state_payload(FULL_STATE))
    named = named_tokens(browser, SCREEN_COLOURS)
    resolved = {one: name for one, name in named.items() if name is not None}
    assert (
        len(resolved) == RESOLVED_COLOURS
    ), f"{len(resolved)} of {len(named)} window colours resolve here: {named}"
    assert resolved == {one: one for one in resolved}, named


def test_the_token_check_would_see_a_colour_no_token_carries(browser: Browser):
    """A colour with no carrier resolves to nothing, so an eight above means eight."""
    draw_window(browser, state_payload(FULL_STATE))
    named = named_tokens(browser, {"UNCARRIED": UNCARRIED_COLOUR})
    assert named == {"UNCARRIED": None}, named
    assert UNCARRIED_COLOUR not in set(dss.TOKENS.values())


def test_a_two_hundred_character_symbol_does_not_widen_the_window(browser: Browser):
    """A CSS box grows to fit where Qt clips, so the header must clip too."""
    payload = payload_for([{"bot": bot(symbol=LONG_NAME)}])
    parts = draw_window(browser, payload)
    line = only(parts, HEADER_LABEL)
    assert line["width"] <= int(HOST_WIDTH_CSS.rstrip("px"))
    assert line["style"]["whiteSpace"] == "nowrap"
    assert line["style"]["overflowX"] == "hidden"


def test_a_header_carrying_a_tag_draws_as_characters_and_loads_nothing(
    browser: Browser,
):
    """The header is a QLabel, which reads a tag as formatting and loads it."""
    browser.js(WATCH_VIOLATIONS)
    payload = payload_for([{"bot": bot(symbol=MARKUP_TEXT)}])
    parts = draw_window(browser, payload)
    browser.settle(SETTLE_MS)
    line = only(parts, HEADER_LABEL)
    assert MARKUP_TEXT in line["text"], f"the tag was not drawn as words: {line}"
    assert "<img" not in line["html"], f"the page built a tag: {line['html']}"
    assert browser.js("document.images.length") == 0
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_image_check_would_see_an_image_the_page_built(browser: Browser):
    draw_window(browser, state_payload(FULL_STATE))
    assert browser.js("document.images.length") == 0
    browser.js("document.body.appendChild(document.createElement('img'));")
    assert browser.js("document.images.length") == 1


@pytest.mark.parametrize("state", ("swarm", "extractor"))
def test_every_tab_is_drawn_once_under_its_own_name(browser: Browser, state: str):
    payload = state_payload(state)
    parts = draw_window(browser, payload)
    drawn = [one["attrs"]["data-key"] for one in at_path(parts, TAB_BUTTON)]
    assert drawn == payload["tabs"]
    for one, name in zip(at_path(parts, TAB_BUTTON), payload["tabs"]):
        assert one["text"] == name


def test_a_reordered_tab_list_is_drawn_in_its_new_order(browser: Browser):
    payload = state_payload(FULL_STATE)
    payload["tabs"] = list(reversed(payload["tabs"]))
    parts = draw_window(browser, payload)
    drawn = [one["attrs"]["data-key"] for one in at_path(parts, TAB_BUTTON)]
    assert drawn == payload["tabs"]


def test_the_named_spaces_are_drawn_empty_and_say_which_unit_fills_each(
    browser: Browser,
):
    """One unit each fills the eight tab pages this window keeps room for."""
    payload = state_payload(FULL_STATE)
    parts = draw_window(browser, payload)
    spaces = browser.parsed("acervatorBotLiveSettings.emptySpaces()")
    assert len(spaces) == len(bls.TAB_PLAN)
    for name in payload["tabs"]:
        page = browser.parsed(
            "acervatorBotLiveSettings.pageOf(" + json.dumps(name) + ")"
        )
        space = only(parts, TAB_PAGES + "/" + page["part"])
        assert space["children"] == 0, f"{name} was drawn into"
        assert space["text"] == "", f"{name} carries words"
        assert space["attrs"]["data-fills"] == page["fills"]


def test_each_page_says_which_side_installs_it_and_whether_it_scrolls(
    browser: Browser,
):
    payload = state_payload(FULL_STATE)
    parts = draw_window(browser, payload)
    for row in payload["tab_plan"]:
        name, _mode, wrapped, installed = row
        if name not in payload["tabs"]:
            continue
        page = browser.parsed(
            "acervatorBotLiveSettings.pageOf(" + json.dumps(name) + ")"
        )
        space = only(parts, TAB_PAGES + "/" + page["part"])
        assert space["attrs"]["data-wrapped"] == json.dumps(wrapped)
        assert space["attrs"]["data-installed"] == installed
        wanted = "auto" if wrapped else "hidden"
        assert space["style"]["overflowY"] == wanted, name


def test_the_extractor_window_keeps_the_positions_space_and_no_fold_space(
    browser: Browser,
):
    payload = state_payload("extractor")
    parts = draw_window(browser, payload)
    drawn = [one["attrs"]["data-key"] for one in at_path(parts, TAB_BUTTON)]
    assert drawn == payload["tabs"]
    assert payload["tab_positions_held"] in drawn
    assert payload["tab_fold_tranches"] not in drawn
    assert at_path(parts, TAB_PAGES + "/positions-held-page")
    assert at_path(parts, TAB_PAGES + "/fold-tranches-page") == []


def test_only_the_chosen_tab_page_is_shown(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_window(browser, payload)
    shown = [one for one in parts if one["attrs"].get("data-current") == "true"]
    pages = [one for one in shown if one["path"].startswith(TAB_PAGES + "/")]
    assert len(pages) == 1, f"{len(pages)} pages are current"
    assert pages[0]["attrs"]["data-index"] == str(payload["current_tab"])


def press(browser: Browser, selector: str) -> list:
    browser.js("window.HOST.querySelector(" + json.dumps(selector) + ").click();")
    return browser.parsed("acervatorBotLiveSettings.sent()")


def test_clicking_a_tab_shows_that_tab_and_hides_the_one_before(browser: Browser):
    payload = state_payload(FULL_STATE)
    draw_window(browser, payload)
    browser.js(
        'window.HOST.querySelector(\'[data-part="tab-button"]'
        '[data-index="2"]\').click();'
    )
    parts = json.loads(browser.js(READ_PARTS))
    current = [
        one
        for one in parts
        if one["path"].startswith(TAB_PAGES + "/")
        and one["attrs"].get("data-current") == "true"
    ]
    assert len(current) == 1, current
    assert current[0]["attrs"]["data-index"] == "2"
    assert current[0]["attrs"]["data-key"] == payload["tabs"][2]


@pytest.mark.parametrize(
    "part, action_name, argument",
    [
        ("prev-button", "prev_clicked", "prev_step"),
        ("next-button", "next_clicked", "next_step"),
    ],
)
def test_each_navigation_button_sends_its_own_step(
    browser: Browser, part: str, action_name: str, argument: str
):
    payload = state_payload(FULL_STATE)
    draw_window(browser, payload)
    assert browser.parsed("acervatorBotLiveSettings.sent()") == []
    sent = press(browser, '[data-part="' + part + '"]')
    assert len(sent) == 1, f"{part} sent {sent}"
    assert sent[0]["action"] == payload["actions"][action_name]
    assert sent[0]["params"] == {"navigate": payload[argument]}


def test_the_apply_button_sends_the_ask_the_surface_names(browser: Browser):
    payload = state_payload("pending")
    draw_window(browser, payload)
    sent = press(browser, '[data-part="apply-button"]')
    assert len(sent) == 1, sent
    assert sent[0]["action"] == payload["actions"]["apply_clicked"]
    assert sent[0]["params"] == {"apply": True}


def test_the_close_button_sends_its_own_action(browser: Browser):
    """`view_model` reads no close parameter, so the ask carries its name alone."""
    payload = state_payload(FULL_STATE)
    draw_window(browser, payload)
    sent = press(browser, '[data-part="close-button"]')
    assert len(sent) == 1, sent
    assert sent[0]["action"] == payload["actions"]["close_clicked"]
    assert sent[0]["params"] == {}


def test_a_disabled_apply_button_sends_nothing(browser: Browser):
    """The button is disabled with no edit, so the check above means something."""
    draw_window(browser, state_payload("alone"))
    press(browser, '[data-part="apply-button"]')
    assert browser.parsed("acervatorBotLiveSettings.sent()") == []


@pytest.mark.parametrize(
    "key, argument",
    [("ArrowLeft", "prev_step"), ("ArrowRight", "next_step")],
)
def test_each_keyboard_shortcut_walks_the_swarm_the_way_qt_does(
    browser: Browser, key: str, argument: str
):
    payload = state_payload(FULL_STATE)
    draw_window(browser, payload)
    browser.js(
        "window.HOST.querySelector('[data-part=\"bot-live-settings\"]')"
        ".dispatchEvent(new KeyboardEvent('keydown', { key: "
        + json.dumps(key)
        + ", ctrlKey: true, bubbles: true }));"
    )
    sent = browser.parsed("acervatorBotLiveSettings.sent()")
    assert len(sent) == 1, sent
    assert sent[0]["params"] == {"navigate": payload[argument]}


def test_an_arrow_with_no_modifier_walks_nowhere(browser: Browser):
    """Qt binds Ctrl with the arrow, so a bare arrow must send nothing."""
    draw_window(browser, state_payload(FULL_STATE))
    browser.js(
        "window.HOST.querySelector('[data-part=\"bot-live-settings\"]')"
        ".dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft',"
        " bubbles: true }));"
    )
    assert browser.parsed("acervatorBotLiveSettings.sent()") == []


def test_a_shortcut_walks_nowhere_where_the_window_wired_none(browser: Browser):
    """A window of one bot wires no shortcut, so the arrow must send nothing."""
    payload = state_payload("alone")
    assert payload["shortcuts"] == []
    draw_window(browser, payload)
    browser.js(
        "window.HOST.querySelector('[data-part=\"bot-live-settings\"]')"
        ".dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight',"
        " ctrlKey: true, bubbles: true }));"
    )
    assert browser.parsed("acervatorBotLiveSettings.sent()") == []


def test_the_window_opens_at_the_size_the_surface_names(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_window(browser, payload)
    wanted = browser.parsed(
        "window.probeStyle('width:"
        + str(payload["opened_size_px"][0])
        + "px', ['width'])"
    )
    assert only(parts, WINDOW)["width"] == int(float(wanted["width"].rstrip("px")))


def test_the_change_line_draws_the_edited_fields_in_the_order_the_surface_sent(
    browser: Browser,
):
    payload = state_payload("two_pending")
    parts = draw_window(browser, payload)
    assert only(parts, CHANGE_LABEL)["text"] == payload["change_label"]
    assert browser.parsed("acervatorBotLiveSettings.editedFields()") == list(
        payload["changes"]
    )


def test_the_page_loads_the_module_after_the_modules_it_reads():
    lines = INDEX_HTML.read_text(encoding="utf-8").splitlines()
    order = [one.strip() for one in lines if "src=" in one]

    def at(name: str) -> int:
        for index, one in enumerate(order):
            if name in one:
                return index
        raise AssertionError(f"{name} is on no script line of {INDEX_HTML.name}")

    mine = at(MODULE_PATH.name)
    for name in (
        "react.production",
        "react-dom.production",
        "design_tokens.js",
        WIDGETS_PATH.name,
        HEADER_PATH.name,
    ):
        assert at(name) < mine, f"{name} loads after {MODULE_PATH.name}"
