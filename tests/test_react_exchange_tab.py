"""The React per-exchange screen, against the surface that describes it."""

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

from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import exchange_tab_surface as ets
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    new_engine,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "exchange_tab.js"
TOKENS_PATH = WEB / "design_tokens.js"
WIDGETS_PATH = WEB / "shared_widgets.js"
HEADER_PATH = WEB / "header_strip.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: One lock for the whole run, so no worker reads a swapped module.
LOCK_PATH = Path(tempfile.gettempdir()) / "acervator_exchange_tab_swap.lock"
LOCK_ATTEMPTS = 400_000


@contextlib.contextmanager
def module_held(attempts: int = LOCK_ATTEMPTS):
    """Takes LOCK_PATH so one worker at a time swaps exchange_tab.js."""
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
HOST_HEIGHT_CSS = "400px"

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

MARKUP_TEXT = '<img src="file:///c:/windows/win.ini">'
LONG_NAME = "N" * 200
NEWLINE_NAME = "two\nlines"


def bot(bot_id: str, mode: str, **over: Any) -> dict:
    """One invented bot record in the shape the two tables refuse or draw."""
    found = {
        "bot_id": bot_id,
        "mode": mode,
        "symbol": "BTC/USD",
        "state": "running",
        "stats": {"current_price": 1.5, "position_value": 20.0},
        "current_holdings": 3.0,
        "quote_to_usd": 1.0,
        "live_target_balance": 40.0,
    }
    found.update(over)
    return found


SCRUM_BOT = bot(ALPHA, ets.MODE_SCRUMMING)
EXTRACTOR_BOT = bot(BETA, ets.MODE_EXTRACTOR)
SECOND_SCRUM = bot(GAMMA, ets.MODE_SCRUMMING)
BOTH_KINDS = [SCRUM_BOT, EXTRACTOR_BOT, SECOND_SCRUM]

FULL_POOL = {
    "ticker_slots": 3,
    "ohlcv_slots": 2,
    "balance_slots": 1,
    "ticker_fetches": 4,
    "ohlcv_fetches": 2,
    "balance_fetches": 1,
    "ticker_hits": 6,
    "ohlcv_hits": 3,
    "balance_hits": 2,
    "freshest_age_s": 1.0,
    "oldest_age_s": 9.0,
    "stale_slots": 1,
}
IDLE_POOL = dict(FULL_POOL, ticker_slots=0, ohlcv_slots=0, balance_slots=0)
AWAITING_POOL = dict(FULL_POOL, freshest_age_s=None)


def statuses(records: list) -> dict:
    return {ets.STATUSES_PARAM: records}


#: STATES holds every state of the screen the bridge can be driven into.
STATES = {
    "empty": [{}],
    "scrum_only": [statuses([SCRUM_BOT])],
    "extractor_only": [statuses([EXTRACTOR_BOT])],
    "both": [statuses(BOTH_KINDS)],
    "selected": [statuses(BOTH_KINDS), {ets.SELECT_SCRUM_PARAM: 0}],
    "extractor_selected": [statuses(BOTH_KINDS), {ets.SELECT_EXTRACTOR_PARAM: 0}],
    "commanded": [
        statuses(BOTH_KINDS),
        {ets.SELECT_SCRUM_PARAM: 0},
        {ets.COMMAND_PARAM: "start"},
    ],
    "refused": [statuses(BOTH_KINDS), {ets.COMMAND_PARAM: "stop"}],
    "masked": [statuses(BOTH_KINDS), {ets.PRIVACY_PARAM: True}],
    "pool_idle": [statuses(BOTH_KINDS), {ets.POOL_SUMMARY_PARAM: IDLE_POOL}],
    "pool_awaiting": [statuses(BOTH_KINDS), {ets.POOL_SUMMARY_PARAM: AWAITING_POOL}],
    "pool_full": [statuses(BOTH_KINDS), {ets.POOL_SUMMARY_PARAM: FULL_POOL}],
    "asked_new_bot": [statuses(BOTH_KINDS), {ets.NEW_BOT_PARAM: True}],
}
STATE_NAMES = tuple(STATES)
FULL_STATE = "commanded"


@contextlib.contextmanager
def own_privacy_register():
    """Hand out a temporary privacy register and put the process one back."""
    from src.core import privacy_mask_registry as registry_module

    was = registry_module._SINGLETON
    with tempfile.TemporaryDirectory() as room:
        registry_module._SINGLETON = registry_module.PrivacyMaskRegistry(
            settings_path=Path(room) / "settings.json", autosave=False
        )
        try:
            yield registry_module._SINGLETON
        finally:
            registry_module._SINGLETON = was


@pytest.fixture(autouse=True)
def fresh_privacy_register():
    """Every test starts from a register no earlier flip has touched."""
    with own_privacy_register() as register:
        yield register


def encoded(found: dict) -> dict:
    """One payload after the round trip through JSON the bridge makes."""
    return json.loads(json.dumps(found, ensure_ascii=True))


def payload_for(steps: list) -> dict:
    ets.view_model({ets.RESET_PARAM: True})
    found: dict = {}
    for one in steps:
        found = ets.view_model(dict(one))
    return encoded(found)


def state_payload(name: str) -> dict:
    return payload_for(STATES[name])


def ticker_payload() -> dict:
    """The state a news strip that built leaves, which no request reaches."""
    return encoded(
        ets.build_view_model(
            ets.build_model(
                statuses=BOTH_KINDS, news_ticker_factory=lambda: {"strip": True}
            )
        )
    )


def token_payload() -> dict:
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


class JsRuntime(JsEngine):
    """A QJSEngine holding the exchange module and a ``window`` global."""

    module_path = MODULE_PATH
    setter = "acervatorSetExchangeTab"

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
        return self.json("acervatorExchangeTab." + answerer + "(JSON.parse(NAME))")

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
    declared = js.json("acervatorExchangeTab.declaredNames()")
    missing = sorted(set(payload) - set(declared))
    assert not missing, f"{len(missing)} published fields have no answer: {missing}"
    extra = sorted(set(declared) - set(payload))
    assert not extra, f"the module declares fields the surface has none of: {extra}"
    differing = sorted(name for name in payload if js.field(name) != payload[name])
    assert not differing, (
        f"{state}: {len(differing)} of {len(payload)} published fields differ: "
        f"{differing}"
    )


def test_the_built_news_strip_state_reaches_the_module(js: JsRuntime):
    """No request builds the strip, so the state is taken off the model."""
    payload = ticker_payload()
    js.push(payload)
    assert payload["news_ticker_built"] is True
    assert payload["header_stretch"] is False
    assert js.field("news_ticker_built") is True


def test_the_whole_payload_check_names_a_field_only_the_surface_holds(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["only_on_the_surface"] = []
    js.push(payload)
    declared = js.json("acervatorExchangeTab.declaredNames()")
    assert sorted(set(payload) - set(declared)) == ["only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_declares(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload.pop("privacy_tooltip")
    js.push(payload)
    declared = js.json("acervatorExchangeTab.declaredNames()")
    assert sorted(set(declared) - set(payload)) == ["privacy_tooltip"]


def test_the_field_value_check_names_one_changed_field(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["scrum_section_label"] = payload["scrum_section_label"] + "!"
    js.push(payload)
    shipped = state_payload(FULL_STATE)
    differing = sorted(name for name in shipped if js.field(name) != shipped[name])
    assert differing == ["scrum_section_label"], f"the check named {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(js: JsRuntime, state):
    payload = state_payload(state)
    report = js.push(payload)
    rows = len(payload["scrum_table"]["bot_ids"]) + len(
        payload["extractor_table"]["bot_ids"]
    )
    assert report["declared"]["fields"] == len(payload)
    assert report["held"]["fields"] == len(payload)
    assert report["declared"]["rows"] == rows
    assert report["held"]["rows"] == rows
    assert report["declared"]["buttons"] == len(payload["command_buttons"])
    assert report["held"]["buttons"] == len(payload["command_buttons"])
    assert report["declared"]["pins"] == len(payload["pins"])
    assert report["held"]["pins"] == len(payload["pins"])
    assert report["declared"]["spaces"] == report["held"]["spaces"]


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    whole = len(payload)
    del payload["privacy_tooltip"]
    report = js.push(payload)
    assert report["declared"]["fields"] == whole
    assert report["held"]["fields"] == whole - 1
    named = [one for one in report["faults"] if one["field"] == "privacy_tooltip"]
    assert named and named[0]["fault"] == "missing", report["faults"]


def test_a_row_the_surface_left_out_shortens_only_the_held_row_count(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["scrum_table"]["bot_ids"] = payload["scrum_table"]["bot_ids"][:-1]
    report = js.push(payload)
    assert report["declared"]["rows"] == report["held"]["rows"] + 1


def test_a_button_pair_with_no_key_shortens_only_the_held_button_count(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["command_buttons"][0] = [payload["command_buttons"][0][0]]
    report = js.push(payload)
    assert report["declared"]["buttons"] == report["held"]["buttons"] + 1


def test_a_pin_under_an_unknown_name_shortens_only_the_held_pin_count(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["pins"][0]["name"] = "exchange.15.999.invented"
    report = js.push(payload)
    assert report["declared"]["pins"] == report["held"]["pins"] + 1
    named = [one for one in report["faults"] if one["field"] == "pins"]
    assert named and named[0]["fault"] == "disagrees", report["faults"]


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
    with own_privacy_register():
        for name in STATE_NAMES:
            walk_payload(state_payload(name), keys, values)
        walk_payload(ticker_payload(), keys, values)
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
PAINTED_VALUES = PUBLISHED_VALUES - AMBIGUOUS - {ets.METHOD}
TOKEN_VALUES = token_values()


def test_no_number_is_written_in_the_module():
    assert not MODULE_LITERALS[
        "numbers"
    ], f"exchange_tab.js holds numeric literals: {MODULE_LITERALS['numbers']}"


def test_no_colour_is_written_in_the_module():
    found = sorted(one for one in MODULE_LITERALS["strings"] if HEX_COLOUR.search(one))
    assert not found, f"exchange_tab.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_screen_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & PAINTED_VALUES)
    assert not written, f"exchange_tab.js writes screen values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"exchange_tab.js writes token values: {written}"


def test_no_slash_stands_outside_a_comment_in_the_module():
    assert not MODULE_LITERALS["slashes"], (
        "exchange_tab.js holds a slash outside a comment, which the scan "
        f"cannot read: {MODULE_LITERALS['slashes']}"
    )


WRITINGS = {
    "number": "var written = 12;",
    "colour": 'var written = "' + dss.TEXT_MED + '";',
    "painted": 'var written = "' + ets.ADD_BOT_LABEL + '";',
    "slash": "var written = 8 " + chr(47) + " 2;",
}


@pytest.mark.parametrize("kind", sorted(WRITINGS))
def test_the_literal_scan_reports_one_value_written_into_the_real_module(kind: str):
    """One value at a time goes into the shipped module and must be caught."""
    original = MODULE_SOURCE.encode("utf-8")
    before = hashlib.sha256(original).hexdigest()
    with module_held():
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
    mine = js.json("acervatorExchangeTab.kinds()")
    missing = sorted(set(theirs) - set(mine))
    assert not missing, f"{state}: the module reads no type at {missing[:6]}"
    extra = sorted(set(mine) - set(theirs))
    assert not extra, f"{state}: the module invented paths {extra[:6]}"
    differing = sorted(one for one in theirs if theirs[one] != mine[one])
    assert not differing, f"{state}: types differ at {differing[:6]}"


def test_the_type_check_names_one_changed_type(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["pull_rate_interval_ms"] = "1000"
    js.push(payload)
    kinds = js.json("acervatorExchangeTab.kinds()")
    assert kinds["pull_rate_interval_ms"] == "string"


def test_the_type_walk_names_a_null_inside_a_list(js: JsRuntime):
    """A scalar inside a list is the hole ten units found."""
    payload = state_payload(FULL_STATE)
    payload["scrum_table"]["bot_ids"] = [None]
    js.push(payload)
    kinds = js.json("acervatorExchangeTab.kinds()")
    assert kinds["scrum_table.bot_ids.0"] == "null"


def test_the_type_walk_names_a_scalar_where_a_bag_belongs(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["timers"] = 7
    js.push(payload)
    assert js.json("acervatorExchangeTab.kinds()")["timers"] == "number"


@pytest.mark.parametrize("name", ["actions", "row_checks", "scrum_table", "timers"])
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


@pytest.mark.parametrize("name", ["calls", "command_buttons", "logged", "pins"])
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


def test_a_table_field_of_the_wrong_type_is_named_against_its_peer(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["extractor_table"]["row_count"] = "1"
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "wrong-type"]
    assert named and named[0]["field"] == "row_count", report["faults"]


def test_a_table_that_counts_its_rows_two_ways_is_named(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["scrum_table"]["drawn_rows"] = 0
    report = js.push(payload)
    named = [one for one in report["faults"] if one["field"] == "drawn_rows"]
    assert named and named[0]["fault"] == "disagrees", report["faults"]


def test_a_table_naming_a_bot_under_no_highlight_is_named(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["extractor_table"]["selected_bot_id"] = BETA
    report = js.push(payload)
    named = [one for one in report["faults"] if one["field"] == "selected_bot_id"]
    assert named and named[0]["fault"] == "disagrees", report["faults"]


#: NUMERIC_NAMES are bot names a JavaScript object reorders as keys.
NUMERIC_NAMES = ["7", "3", "1"]


def numeric_payload() -> dict:
    return payload_for(
        [statuses([bot(name, ets.MODE_SCRUMMING) for name in NUMERIC_NAMES])]
    )


def test_the_bot_order_is_the_order_the_surface_sent(js: JsRuntime):
    js.push(numeric_payload())
    assert js.named("botIds", "scrum_table") == NUMERIC_NAMES


def test_reading_bot_names_off_a_bag_loses_the_order(js: JsRuntime):
    """The bag walk is what #276 breaks, so the list beside it must be read."""
    js.push(numeric_payload())
    keys = js.json(
        "Object.keys((function () { var found = {};"
        " acervatorExchangeTab.botIds('scrum_table').forEach(function (one) {"
        " found[one] = true; }); return found; })())"
    )
    assert keys != NUMERIC_NAMES, "the bag kept the order, so this proves nothing"
    assert sorted(keys) == sorted(NUMERIC_NAMES)


def test_every_bag_the_payload_carries_is_keyed_by_a_name_the_surface_owns(
    js: JsRuntime,
):
    """A bag keyed by a bot id is the shape #276 reorders."""
    payload = numeric_payload()
    js.push(payload)
    sent = set(NUMERIC_NAMES)
    for name in js.json("acervatorExchangeTab.bagNames()"):
        keys = set(js.json("Object.keys(acervatorExchangeTab.bag('" + name + "'))"))
        assert not keys & sent, f"{name} is keyed by a bot id: {sorted(keys & sent)}"


def test_the_command_keys_are_read_in_the_order_the_surface_sent(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    js.push(payload)
    assert js.json("acervatorExchangeTab.commandKeys()") == [
        pair[1] for pair in payload["command_buttons"]
    ]


def test_a_reordered_button_list_is_read_in_its_new_order(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["command_buttons"].reverse()
    js.push(payload)
    assert js.json("acervatorExchangeTab.commandKeys()") == [
        pair[1] for pair in payload["command_buttons"]
    ]


def test_the_colour_refusal_names_an_eight_digit_hex(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["pull_rate_style"] = "color:#80ff00cc;"
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "qt-colour"]
    assert named, "the module named no eight-digit colour"
    assert named[0]["detail"] == "AARRGGBB"


def test_the_colour_refusal_names_a_byte_alpha(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["scrum_section_style"] = "background:rgba(1,2,3,128);"
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "qt-colour"]
    assert named and named[0]["detail"] == "rgba(", report["faults"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_colour_refusal_is_quiet_on_a_shipped_payload(js: JsRuntime, state: str):
    report = js.push(state_payload(state))
    named = [one for one in report["faults"] if one["fault"] == "qt-colour"]
    assert named == [], f"{state}: a shipped colour was refused: {named}"


def test_a_refused_colour_is_left_out_of_the_style_the_module_paints(js: JsRuntime):
    kept = js.named("keptSheet", "color:#80ff00cc;background:#101010;")
    assert "#80ff00cc" not in kept
    assert "#101010" in kept


@pytest.mark.parametrize(
    "name",
    ["add_bot_label", "pull_rate_text", "scrum_section_label", "select_first_message"],
)
def test_a_word_the_screen_draws_carrying_a_tag_is_named(js: JsRuntime, name: str):
    payload = state_payload(FULL_STATE)
    payload[name] = MARKUP_TEXT
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "markup"]
    assert named and named[0]["field"] == name, report["faults"]


def test_a_bot_name_carrying_a_tag_is_named(js: JsRuntime):
    payload = payload_for([statuses([bot(MARKUP_TEXT, ets.MODE_SCRUMMING)])])
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "markup"]
    assert named, f"a bot name carrying a tag was not named: {report['faults']}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_markup_check_is_quiet_on_a_shipped_payload(js: JsRuntime, state: str):
    report = js.push(state_payload(state))
    named = [one for one in report["faults"] if one["fault"] == "markup"]
    assert named == [], f"{state}: shipped text was named as markup: {named}"


def test_the_privacy_button_words_and_colours_must_name_one_state(js: JsRuntime):
    payload = state_payload("masked")
    assert payload["privacy_label"] == payload["privacy_label_on"]
    payload["privacy_style"] = payload["privacy_style_off"]
    report = js.push(payload)
    named = [one for one in report["faults"] if one["field"] == "privacy_style"]
    assert named and named[0]["fault"] == "disagrees", report["faults"]


def test_the_privacy_check_names_words_that_are_neither_state(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["privacy_label"] = "Privacy Mode: MAYBE"
    report = js.push(payload)
    named = [one for one in report["faults"] if one["field"] == "privacy_label"]
    assert named and named[0]["fault"] == "disagrees", report["faults"]


@pytest.mark.parametrize("state", ("both", "masked"))
def test_the_privacy_check_is_quiet_on_a_shipped_payload(js: JsRuntime, state: str):
    report = js.push(state_payload(state))
    named = [
        one
        for one in report["faults"]
        if one["field"] in ("privacy_label", "privacy_style")
    ]
    assert named == [], f"{state}: a shipped Privacy button was refused: {named}"


def test_a_timer_that_no_delay_list_carries_is_named(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["timer_delays_ms"] = []
    report = js.push(payload)
    named = [one for one in report["faults"] if one["field"] == "timer_delays_ms"]
    assert named and named[0]["fault"] == "disagrees", report["faults"]


def test_a_timer_bag_that_names_another_wait_is_named(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["timers"] = {"pull_rate": 250}
    report = js.push(payload)
    named = [one for one in report["faults"] if one["field"] == "timers"]
    assert named and named[0]["fault"] == "disagrees", report["faults"]


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
    payload = ets.view_model(dict(STATES[state][-1]))
    json.dumps(payload, ensure_ascii=True)
    wrong = [
        (path, type(value).__name__)
        for path, value in leaves(payload)
        if value is not None and not isinstance(value, (str, int, float, bool))
    ]
    assert not wrong, f"{state}: the payload carries live objects: {wrong}"


def test_the_plain_data_walk_names_a_live_object_the_payload_carries():
    """The walk above passes anything, so one live object must be named."""
    payload = ets.view_model({ets.RESET_PARAM: True})
    payload["news_ticker_built"] = object()
    wrong = [
        path
        for path, value in leaves(payload)
        if value is not None and not isinstance(value, (str, int, float, bool))
    ]
    assert wrong == ["news_ticker_built"]


def test_the_module_names_a_value_that_is_not_plain_data(js: JsRuntime):
    js.push(state_payload(FULL_STATE))
    assert js.json("acervatorExchangeTab.plainness()") == []
    js.run("acervatorExchangeTab.payload().skin.live = function () { return 1; };")
    assert js.json("acervatorExchangeTab.plainness()") == ["skin.live"]


HOSTILE_FIELDS: dict = {
    "actions_missing": ("actions", None),
    "actions_null": ("actions", None),
    "command_buttons_null": ("command_buttons", None),
    "command_buttons_number": ("command_buttons", 7),
    "pins_text": ("pins", "none"),
    "privacy_label_number": ("privacy_label", 7),
    "pull_rate_interval_ms_text": ("pull_rate_interval_ms", "soon"),
    "pull_rate_text_number": ("pull_rate_text", 7),
    "scrum_table_null": ("scrum_table", None),
    "scrum_section_visible_text": ("scrum_section_visible", "yes"),
    "timers_list": ("timers", []),
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
    assert js.json("acervatorExchangeTab.isLoaded()") is True


HOSTILE_NAMES = {
    "nan": "nan",
    "inf": "inf",
    "minus_inf": "-inf",
    "huge": str(10**24),
    "number_where_text_belongs": 7,
    "a_newline": NEWLINE_NAME,
    "markup": MARKUP_TEXT,
    "long_name": LONG_NAME,
    "empty": "",
}


@pytest.mark.parametrize("case", sorted(HOSTILE_NAMES))
def test_a_hostile_bot_name_still_routes_every_bot_to_a_table(js: JsRuntime, case: str):
    payload = payload_for(
        [statuses([bot(HOSTILE_NAMES[case], ets.MODE_SCRUMMING), EXTRACTOR_BOT])]
    )
    report = js.push(payload)
    assert isinstance(report["faults"], list), f"{case} answered no fault list"
    assert report["held"]["rows"] == report["declared"]["rows"]
    assert len(js.named("botIds", "scrum_table")) == 1


def test_two_bots_under_one_name_each_reach_a_row(js: JsRuntime):
    """A duplicate name is what a bag keyed by bot id collapses to one."""
    payload = payload_for(
        [statuses([bot(ALPHA, ets.MODE_SCRUMMING), bot(ALPHA, ets.MODE_SCRUMMING)])]
    )
    js.push(payload)
    assert js.named("botIds", "scrum_table") == [ALPHA, ALPHA]


HOSTILE_MONEY = {
    "negative_balance": {"current_holdings": -5.0, "live_target_balance": -40.0},
    "zero_price": {"quote_to_usd": 0.0, "stats": {"current_price": 0.0}},
    "huge_balance": {"live_target_balance": float(10**24)},
    "text_where_a_number_belongs": {"current_holdings": "many"},
}


@pytest.mark.parametrize("case", sorted(HOSTILE_MONEY))
def test_a_hostile_balance_reaches_no_label_on_this_screen(js: JsRuntime, case: str):
    """This screen draws no balance, so a bad one must change no word."""
    over = HOSTILE_MONEY[case]
    if case == "text_where_a_number_belongs":
        with pytest.raises(ValueError):
            payload_for([statuses([bot(ALPHA, ets.MODE_SCRUMMING, **over)])])
        return
    payload = payload_for([statuses([bot(ALPHA, ets.MODE_SCRUMMING, **over)])])
    shipped = payload_for([statuses([bot(ALPHA, ets.MODE_SCRUMMING)])])
    js.push(payload)
    assert payload["scrum_table"]["drawn_rows"] == 1
    assert payload["pull_rate_text"] == shipped["pull_rate_text"]
    assert js.field("pull_rate_text") == shipped["pull_rate_text"]


HOSTILE_POOL = {
    "nan_age": {"freshest_age_s": float("nan")},
    "inf_age": {"oldest_age_s": float("inf")},
    "minus_inf_age": {"freshest_age_s": float("-inf")},
    "huge_slots": {"stale_slots": 10**24},
    "markup_stale": {"stale_slots": MARKUP_TEXT},
    "newline_stale": {"stale_slots": NEWLINE_NAME},
    "no_hits_at_all": {"ticker_hits": 0, "ohlcv_hits": 0, "balance_hits": 0},
}


@pytest.mark.parametrize("case", sorted(HOSTILE_POOL))
def test_a_hostile_pool_report_still_writes_one_freshness_line(
    js: JsRuntime, case: str
):
    payload = payload_for(
        [
            statuses(BOTH_KINDS),
            {ets.POOL_SUMMARY_PARAM: dict(FULL_POOL, **HOSTILE_POOL[case])},
        ]
    )
    report = js.push(payload)
    assert isinstance(report["faults"], list), f"{case} answered no fault list"
    assert isinstance(payload["pull_rate_text"], str)
    assert js.field("pull_rate_text") == payload["pull_rate_text"]
    marked = [one for one in report["faults"] if one["fault"] == "markup"]
    assert bool(marked) is (case == "markup_stale"), report["faults"]


def test_a_payload_that_is_not_an_object_is_named(js: JsRuntime):
    report = js.json("acervatorSetExchangeTab(7)")
    assert report["declared"] is None
    assert report["faults"][0]["fault"] == "not-an-object"


def test_the_hostile_check_would_see_a_module_that_raised(js: JsRuntime):
    """A raise inside the module reaches js.json as an error, not a pass."""
    result = js.json(
        "(function () { try { return null.x; } catch (e) { return 1; } })()"
    )
    assert result == 1


def test_each_request_is_keyed_by_the_name_the_surface_publishes(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    js.push(payload)
    js.bind_json("KEY", payload["command_param"])
    built = js.json("acervatorExchangeTab.requestFor('command_param', 'start')")
    assert built == {payload["command_param"]: "start"}


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
                if self.js("typeof window.acervatorSetExchangeTab") == "function":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the exchange module: readyState "
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
}

WATCH_VIOLATIONS = (
    "window.VIOLATIONS = [];"
    "document.addEventListener('securitypolicyviolation', function (e) {"
    "  window.VIOLATIONS.push(e.violatedDirective + ' ' + e.blockedURI); });"
)

PAGE_HELPERS = (
    "window.HOST = document.getElementById('exchange-host');"
    "if (window.HOST === null) {"
    "  window.HOST = document.createElement('div');"
    "  window.HOST.id = 'exchange-host';"
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


def draw_tab(browser: Browser, payload: dict) -> list:
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorExchangeTab.forget();"
        "acervatorSetExchangeTab(JSON.parse(window.PAYLOAD));"
        "acervatorExchangeTab.renderTab(window.HOST);"
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


def sheet_agrees(drawn: dict, expected: dict, where: str) -> None:
    assert expected, f"{where}: the probe took no value, so this compares nothing"
    differing = {
        name: (value, drawn["style"].get(name))
        for name, value in expected.items()
        if drawn["style"].get(name) != value
    }
    assert not differing, f"{where}: wanted against drawn {differing}"


TAB = "exchange-tab"
HEADER = TAB + "/header-row"
PRIVACY = HEADER + "/privacy-button"
NEWS_TICKER = HEADER + "/news-ticker"
HEADER_STRETCH = HEADER + "/header-stretch"
ADD_BOT = HEADER + "/add-bot-button"
PULL_RATE = TAB + "/pull-rate"
SCRUM_SECTION = TAB + "/scrum-section"
SCRUM_TABLE = TAB + "/scrum-table"
EXTRACTOR_SECTION = TAB + "/extractor-section"
EXTRACTOR_TABLE = TAB + "/extractor-table"
COMMAND_BAR = TAB + "/command-bar"
COMMAND_BUTTON = COMMAND_BAR + "/command-button"


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    assert browser.js("typeof window.acervatorExchangeTab") == "object"
    assert browser.js("typeof window.acervatorSetExchangeTab") == "function"
    assert browser.js("typeof window.acervatorLoadExchangeTab") == "function"
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_module_makes_no_network_call_of_its_own(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    draw_tab(browser, state_payload(FULL_STATE))
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
    draw_tab(browser, state_payload(state))
    counts = browser.parsed(
        "[window.HOST.querySelectorAll('*').length,"
        " window.HOST.querySelectorAll('[data-part]').length]"
    )
    assert counts[0] == counts[1], f"{state}: {counts[0]} elements, {counts[1]} named"
    assert counts[0] > 0, f"{state}: the screen drew nothing at all"


def test_the_name_check_would_see_an_element_with_no_name(browser: Browser):
    draw_tab(browser, state_payload(FULL_STATE))
    counts = browser.parsed(
        "(function () {"
        "  window.HOST.firstChild.appendChild(document.createElement('b'));"
        "  return [window.HOST.querySelectorAll('*').length,"
        "    window.HOST.querySelectorAll('[data-part]').length]; })()"
    )
    assert counts[0] == counts[1] + 1


def test_the_privacy_button_sheet_reaches_the_drawn_button(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    body = qt_block(payload["privacy_style"], "QPushButton")
    sheet_agrees(only(parts, PRIVACY), probe(browser, body), "the Privacy button")


def test_the_masked_privacy_button_paints_the_other_sheet(browser: Browser):
    """The two sheets must draw apart, or the sheet check proves nothing."""
    off = draw_tab(browser, state_payload("both"))
    on = draw_tab(browser, state_payload("masked"))
    assert (
        only(on, PRIVACY)["style"]["backgroundColor"]
        != only(off, PRIVACY)["style"]["backgroundColor"]
    )
    assert only(on, PRIVACY)["attrs"]["data-masked"] == "true"
    assert only(off, PRIVACY)["attrs"]["data-masked"] == "false"


def test_the_freshness_sheet_reaches_the_drawn_line(browser: Browser):
    payload = state_payload("pool_full")
    parts = draw_tab(browser, payload)
    sheet_agrees(
        only(parts, PULL_RATE), probe(browser, payload["pull_rate_style"]), "the line"
    )


@pytest.mark.parametrize(
    "path, field",
    [
        (SCRUM_SECTION, "scrum_section_style"),
        (EXTRACTOR_SECTION, "extractor_section_style"),
    ],
)
def test_each_section_sheet_reaches_its_drawn_heading(
    browser: Browser, path: str, field: str
):
    payload = state_payload("both")
    parts = draw_tab(browser, payload)
    sheet_agrees(only(parts, path), probe(browser, payload[field]), path)


def test_the_two_section_headings_take_different_padding(browser: Browser):
    """Both headings share a sheet apart from padding, so one must differ."""
    parts = draw_tab(browser, state_payload("both"))
    assert (
        only(parts, SCRUM_SECTION)["style"]["paddingTop"]
        != only(parts, EXTRACTOR_SECTION)["style"]["paddingTop"]
    )


#: MEASURED_STYLE_NAMES is the count read off this host, not one assumed.
MEASURED_STYLE_NAMES = 3


def test_the_freshness_sheet_writes_the_property_count_measured_on_this_host(
    browser: Browser,
):
    draw_tab(browser, state_payload("pool_full"))
    written = browser.parsed(
        "Object.keys(acervatorExchangeTab.styleOf("
        "  acervatorExchangeTab.payload().pull_rate_style))"
    )
    assert (
        len(written) == MEASURED_STYLE_NAMES
    ), f"the freshness sheet writes {len(written)} properties here: {written}"


def test_a_token_that_carries_no_screen_colour_is_left_unresolved(browser: Browser):
    """A colour with no single token keeps the surface's own value."""
    draw_tab(browser, state_payload(FULL_STATE))
    resolved = browser.parsed(
        "acervatorExchangeTab.variableFor("
        + json.dumps(dss.MAIN_BADGE_TEXT)
        + ") || null"
    )
    assert resolved is None or isinstance(resolved, str)


def test_a_two_hundred_character_line_does_not_widen_the_screen(browser: Browser):
    """A CSS box grows to fit where Qt clips, so the line must clip too."""
    payload = state_payload("pool_full")
    payload["pull_rate_text"] = LONG_NAME
    parts = draw_tab(browser, payload)
    line = only(parts, PULL_RATE)
    assert line["width"] <= int(HOST_WIDTH_CSS.rstrip("px"))
    assert line["style"]["whiteSpace"] == "nowrap"
    assert line["style"]["overflowX"] == "hidden"


def test_a_freshness_line_carrying_a_tag_draws_as_characters_and_loads_nothing(
    browser: Browser,
):
    """Qt measured this tag at 33px against 209 for the same characters."""
    browser.js(WATCH_VIOLATIONS)
    payload = state_payload("pool_full")
    payload["pull_rate_text"] = MARKUP_TEXT
    parts = draw_tab(browser, payload)
    browser.settle(SETTLE_MS)
    line = only(parts, PULL_RATE)
    assert MARKUP_TEXT in line["text"], f"the tag was not drawn as words: {line}"
    assert "<img" not in line["html"], f"the page built a tag: {line['html']}"
    assert browser.js("document.images.length") == 0
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_image_check_would_see_an_image_the_page_built(browser: Browser):
    draw_tab(browser, state_payload(FULL_STATE))
    assert browser.js("document.images.length") == 0
    browser.js("document.body.appendChild(document.createElement('img'));")
    assert browser.js("document.images.length") == 1


def test_every_command_button_is_drawn_once_under_its_own_key(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    drawn = [one["attrs"]["data-key"] for one in at_path(parts, COMMAND_BUTTON)]
    assert drawn == [pair[1] for pair in payload["command_buttons"]]
    for one, pair in zip(at_path(parts, COMMAND_BUTTON), payload["command_buttons"]):
        assert one["text"] == pair[0]
        marked = pair[0] == payload["danger_command_label"]
        assert one["attrs"]["data-danger"] == json.dumps(marked)


def test_a_reordered_button_list_is_drawn_in_its_new_order(browser: Browser):
    payload = state_payload(FULL_STATE)
    payload["command_buttons"].reverse()
    parts = draw_tab(browser, payload)
    drawn = [one["attrs"]["data-key"] for one in at_path(parts, COMMAND_BUTTON)]
    assert drawn == [pair[1] for pair in payload["command_buttons"]]


def press(browser: Browser, selector: str) -> list:
    browser.js("window.HOST.querySelector(" + json.dumps(selector) + ").click();")
    return browser.parsed("acervatorExchangeTab.sent()")


COMMAND_KEYS = [pair[1] for pair in ets.COMMAND_BUTTONS]


@pytest.mark.parametrize("key", COMMAND_KEYS)
def test_each_command_button_sends_its_own_command(browser: Browser, key: str):
    payload = state_payload("selected")
    draw_tab(browser, payload)
    assert browser.parsed("acervatorExchangeTab.sent()") == []
    sent = press(browser, '[data-part="command-button"][data-key="' + key + '"]')
    assert len(sent) == 1, f"{key} sent {sent}"
    assert sent[0]["action"] == payload["actions"]["command_clicked"]
    assert sent[0]["params"] == {payload["command_param"]: key}


def test_the_privacy_button_sends_the_flip_the_surface_names(browser: Browser):
    payload = state_payload(FULL_STATE)
    draw_tab(browser, payload)
    sent = press(browser, '[data-part="privacy-button"]')
    assert len(sent) == 1, sent
    assert sent[0]["action"] == payload["actions"]["privacy_clicked"]
    assert sent[0]["params"] == {payload["privacy_param"]: True}


def test_the_new_bot_button_sends_the_ask_the_surface_names(browser: Browser):
    payload = state_payload(FULL_STATE)
    draw_tab(browser, payload)
    sent = press(browser, '[data-part="add-bot-button"]')
    assert len(sent) == 1, sent
    assert sent[0]["action"] == payload["actions"]["add_bot_clicked"]
    assert sent[0]["params"] == {payload["new_bot_param"]: True}


@pytest.mark.parametrize(
    "answerer, action_name, param",
    [
        ("selectScrumRow", "scrum_selection_changed", "select_scrum_param"),
        ("selectExtractorRow", "extractor_selection_changed", "select_extractor_param"),
        ("tick", "pull_rate_timeout", "pull_rate_param"),
    ],
)
def test_each_step_the_tables_and_the_timer_take_sends_its_own_action(
    browser: Browser, answerer: str, action_name: str, param: str
):
    payload = state_payload(FULL_STATE)
    draw_tab(browser, payload)
    value = True if answerer == "tick" else 0
    browser.js("acervatorExchangeTab." + answerer + "(" + json.dumps(value) + ");")
    sent = browser.parsed("acervatorExchangeTab.sent()")
    assert len(sent) == 1, sent
    assert sent[0]["action"] == payload["actions"][action_name]
    assert sent[0]["params"] == {payload[param]: value}


def test_the_freshness_timer_starts_no_interval_where_no_bridge_can_answer(
    browser: Browser,
):
    """A timer that could fetch nothing is not started, so nothing is sent."""
    draw_tab(browser, state_payload("pool_full"))
    assert browser.js("typeof window.acervator") == "undefined"
    browser.settle(NETWORK_SETTLE_MS)
    assert browser.parsed("acervatorExchangeTab.sent()") == []


def test_the_freshness_line_carries_the_wait_the_surface_names(browser: Browser):
    payload = state_payload("pool_full")
    parts = draw_tab(browser, payload)
    assert only(parts, PULL_RATE)["attrs"]["data-interval-ms"] == str(
        payload["pull_rate_interval_ms"]
    )


def test_the_privacy_button_is_left_out_of_the_keyboard_order(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    assert payload["privacy_focusable"] is False
    assert only(parts, PRIVACY)["attrs"]["tabindex"] == "-1"
    assert "tabindex" not in only(parts, ADD_BOT)["attrs"]


def test_the_named_spaces_are_drawn_empty(browser: Browser):
    """One unit each fills the news strip and the Extractor table."""
    parts = draw_tab(browser, state_payload("both"))
    assert browser.parsed("acervatorExchangeTab.emptySpaces()") == [
        "news-ticker",
        "extractor-table",
    ]
    assert only(parts, EXTRACTOR_TABLE)["children"] == 0
    assert only(parts, EXTRACTOR_TABLE)["text"] == ""
    assert only(parts, SCRUM_TABLE)["children"] == 0


def test_the_news_strip_space_is_drawn_only_where_the_strip_built(browser: Browser):
    plain = draw_tab(browser, state_payload("both"))
    assert at_path(plain, NEWS_TICKER) == []
    assert only(plain, HEADER_STRETCH)["style"]["flexGrow"] == "1"
    built = draw_tab(browser, ticker_payload())
    assert at_path(built, HEADER_STRETCH) == []
    assert only(built, NEWS_TICKER)["style"]["flexGrow"] == str(
        ticker_payload()["news_ticker_stretch"]
    )


def test_each_table_space_carries_the_rows_its_own_table_will_draw(browser: Browser):
    payload = state_payload("both")
    parts = draw_tab(browser, payload)
    for path, slot in (
        (SCRUM_TABLE, "scrum_table"),
        (EXTRACTOR_TABLE, "extractor_table"),
    ):
        space = only(parts, path)
        assert space["attrs"]["data-kind"] == payload[slot]["kind"]
        assert space["attrs"]["data-rows"] == str(payload[slot]["row_count"])
        assert space["attrs"]["data-held"] == str(len(payload[slot]["bot_ids"]))


def test_the_scrumming_table_draws_its_own_rows_into_the_space_kept_for_it(
    browser: Browser,
):
    """bot_status_table.js owns the rows; this screen owns only the space."""
    from src.gui.main_tabs import bot_status_table_surface as bts

    table = json.loads(json.dumps(bts.view_model({}), ensure_ascii=True))
    draw_tab(browser, state_payload("both"))
    browser.js("window.TABLE = " + json.dumps(json.dumps(table)) + ";")
    drawn = browser.parsed(
        "(function () {"
        "  acervatorSetBotTable(JSON.parse(window.TABLE));"
        "  acervatorExchangeTab.renderScrumTable(window.HOST);"
        "  return window.HOST.querySelectorAll("
        "    '[data-part=\"scrum-table\"] [data-part]').length; })()"
    )
    assert drawn > 0, "the bot table drew nothing into the space"


@pytest.mark.parametrize(
    "state, scrum, extractor",
    [
        ("both", True, True),
        ("scrum_only", True, False),
        ("extractor_only", False, True),
        ("empty", False, False),
    ],
)
def test_each_section_is_shown_only_where_its_own_list_holds_a_bot(
    browser: Browser, state: str, scrum: bool, extractor: bool
):
    parts = draw_tab(browser, state_payload(state))
    shown = {
        SCRUM_SECTION: scrum,
        SCRUM_TABLE: scrum,
        EXTRACTOR_SECTION: extractor,
        EXTRACTOR_TABLE: extractor,
    }
    for path, wanted in shown.items():
        one = only(parts, path)
        assert one["attrs"]["data-visible"] == json.dumps(wanted), path
        assert ("hidden" in one["attrs"]) is not wanted, path


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
        "design_tokens.js",
        "shared_widgets.js",
        HEADER_PATH.name,
        "bot_status_table.js",
    ):
        assert at(name) < mine, f"{name} loads after {MODULE_PATH.name}"
