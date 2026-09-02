"""Drives `journal_tab.js` against `journal_tab_surface.py`."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import journal_tab_surface as jts
from src.gui.main_tabs import theme_engine_surface as tes
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    drain_events,
    js_literals,
    new_engine,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "journal_tab.js"
TOKENS_PATH = WEB / "design_tokens.js"
THEMES_PATH = WEB / "theme_engine.js"
WIDGETS_PATH = WEB / "shared_widgets.js"
CELLS_PATH = WEB / "table_cells.js"
HEADER_PATH = WEB / "header_strip.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: MODULE_TAIL is the closing line a whole module file ends with.
MODULE_TAIL = "})(window);"

MODULE_READ_ATTEMPTS = 200
#: A pause between reads, so retrying does not hold MODULE_PATH open
#: against the os.replace in another worker.
MODULE_READ_PAUSE_S = 0.01


def read_module() -> str:
    """Return MODULE_PATH text ending with MODULE_TAIL, retrying while not."""
    for _ in range(MODULE_READ_ATTEMPTS):
        found = MODULE_PATH.read_text(encoding="utf-8")
        if found.rstrip().endswith(MODULE_TAIL):
            return found
        time.sleep(MODULE_READ_PAUSE_S)
    raise AssertionError(MODULE_PATH.name + " never read back whole")


#: MODULE_SOURCE is read at collection, before any test body writes.
MODULE_SOURCE = read_module()

JS_TIMEOUT_MS = 30_000
SETTLE_MS = 500
NETWORK_SETTLE_MS = 1500
READY_ROUNDS = 100
READY_STEP_MS = 100
#: A script whose file another worker is swapping can fail to load once.
PAGE_LOAD_ATTEMPTS = 4

#: HOST_WIDTH_PX is set because an unshown view reads ``clientWidth`` as zero.
HOST_WIDTH_PX = 1400
HOST_HEIGHT_PX = 900
VIEW_SIZE_PX = (1400, 900)

#: JS_TYPE_OF maps a Python type name to its type after ``json.dumps``.
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

#: NAMED_VALUE is the bridge method the module asks on, not a painted value.
NAMED_VALUE = jts.METHOD

#: NAME_LISTS holds each published list whose entries name a slot.
NAME_LISTS = ("children", "header_order", "recovery_order", "button_row_order")
#: NAME_FIELDS holds each published field whose value names a rule.
NAME_FIELDS = ("orientation", "cell_alignment")

#: NAMED_SUB_KEYS holds the nested key names the module reads by name.
NAMED_SUB_KEYS = {
    "alternating_row_colors",
    "bold",
    "cell_alignment",
    "cell_alignment_value",
    "children",
    "children_collapsible",
    "column_count",
    "columns",
    "edit_triggers",
    "enabled",
    "font_family",
    "font_point_size",
    "gap",
    "handle_width_px",
    "header_resize_mode",
    "indent",
    "index",
    "items",
    "label",
    "label_color",
    "line_defaults",
    "margins_px",
    "minimum_width_px",
    "orientation",
    "read_only",
    "requested_sizes_px",
    "row_colors",
    "row_count",
    "rows",
    "selection_behavior",
    "signals_blocked",
    "spacing_px",
    "style_sheet",
    "text",
    "title",
    "value",
    "value_color",
    "vertical_header_visible",
    "bot_filter.currentIndexChanged",
    "period_filter.currentIndexChanged",
    "journal_table.currentCellChanged",
}


def entry(**named: Any) -> dict:
    """One completed trade entry, with the timestamp and price a journal keeps."""
    found = {
        "timestamp": 1700000000,
        "bot_id": "alpha-one-and-longer",
        "symbol": "BTC/USD",
        "action": "scrum",
        "side": "sell",
        "price": 60000.0,
        "quantity": 0.02,
        "cost": 1200.0,
        "pnl": 12.5,
        "ta_direction": jts.BULLISH,
        "ta_confidence": 0.75,
        "ta_timeframe": "1h",
        "exchange_id": "coinbase",
        "order_id": "ord-1",
        "execution_strategy": "market",
        "slippage_pct": 0.0125,
        "reason": "target reached and then some more words",
    }
    found.update(named)
    return found


THREE_ENTRIES = [
    entry(),
    entry(
        bot_id="beta-two-and-longer",
        symbol="ETH/USD",
        action="fold",
        side="buy",
        pnl=-3.25,
        ta_direction=jts.BEARISH,
        reason="dip bought",
    ),
    entry(
        bot_id="gamma-three-longer",
        symbol="SOL/USD",
        pnl=0.0,
        ta_direction="NEUTRAL",
        reason="held",
    ),
]

VOTED_ENTRY = entry(
    ta_signals={"rsi": jts.BULLISH, "macd": jts.BEARISH, "bb": "NEUTRAL"}
)

STATISTICS = {"total_entries": 3, "unique_bots": 3, "total_pnl": 9.25}

BOT_STATUSES = [
    {"bot_id": "alpha-one-and-longer", "symbol": "BTC/USD"},
    {"bot_id": "beta-two-and-longer", "symbol": "ETH/USD"},
]

RECOVERY_INFO = {"has_snapshot": True, "snapshot_age": 95.0, "snapshot_bots": 4}
NO_SNAPSHOT_INFO = {"has_snapshot": False, "journal_files": 7}
RECON_RESULT = {"timestamp": 1700000500, "exchange": "coinbase", "orphaned_count": 2}

#: STATES holds each published state as the calls that reach it.
STATES = {
    "empty": (),
    "one": ({"statistics": STATISTICS, "entries": [entry()]},),
    "three": ({"statistics": STATISTICS, "entries": THREE_ENTRIES},),
    "selected": (
        {"statistics": STATISTICS, "entries": THREE_ENTRIES, "selected_row": 1},
    ),
    "voted": ({"statistics": STATISTICS, "entries": [VOTED_ENTRY], "selected_row": 0},),
    "filtered": (
        {
            "statistics": STATISTICS,
            "entries": THREE_ENTRIES,
            "bot_statuses": BOT_STATUSES,
        },
    ),
    "recovered": (
        {
            "statistics": STATISTICS,
            "entries": THREE_ENTRIES,
            "recovery_info": RECOVERY_INFO,
            "reconciliation_result": RECON_RESULT,
        },
    ),
    "no_snapshot": (
        {
            "statistics": STATISTICS,
            "entries": THREE_ENTRIES,
            "recovery_info": NO_SNAPSHOT_INFO,
        },
    ),
}
STATE_NAMES = tuple(STATES)


def bridge_payload(*calls: dict) -> dict:
    """Return `jts.view_model` output after a reset and each `calls` entry,
    through `json.dumps`."""
    found = jts.view_model({"reset": True})
    for params in calls:
        found = jts.view_model(dict(params))
    return json.loads(json.dumps(found, ensure_ascii=True))


def state_payload(name: str) -> dict:
    return bridge_payload(*STATES[name])


def token_payload() -> dict:
    """Return `dss.view_model` output through the bridge's `json.dumps`."""
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


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


def naming_values(node: Any, found: set) -> None:
    """Every published string naming one slot or one rule, added to `found`."""
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(key)
            if key in NAME_LISTS and isinstance(value, list):
                found.update(one for one in value if isinstance(one, str))
            if key in NAME_FIELDS and isinstance(value, str):
                found.add(value)
            naming_values(value, found)
        return
    if isinstance(node, list):
        for one in node:
            naming_values(one, found)


def published() -> tuple:
    """Every key name and every string value, over every state."""
    keys: set = set()
    values: set = set()
    for name in STATE_NAMES:
        walk_payload(state_payload(name), keys, values)
    values.discard("")
    keys.discard("")
    return keys, values


def named_slots() -> set:
    found: set = set()
    for name in STATE_NAMES:
        naming_values(state_payload(name), found)
    found.discard("")
    return found


def as_css(value: Any) -> set:
    """One token value in every spelling a stylesheet could carry."""
    if isinstance(value, str):
        return {value}
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return {str(value)}
    return set()


def token_values() -> set:
    """Every value the token and theme tables carry, in CSS spelling."""
    found: set = set()
    for value in dss.TOKENS.values():
        found |= as_css(value)
    for theme in tes.THEMES.values():
        for value in theme.values():
            found |= as_css(value)
    found.discard("")
    return found


PUBLISHED_KEYS, PUBLISHED_VALUES = published()
NAMING_VALUES = named_slots()
PAINTED_VALUES = PUBLISHED_VALUES - NAMING_VALUES - {NAMED_VALUE}
TOKEN_VALUES = token_values()
MODULE_LITERALS = js_literals(MODULE_SOURCE)


class JsRuntime(JsEngine):
    """A QJSEngine holding ``journal_tab.js``."""

    module_path = MODULE_PATH
    setter = "acervatorSetJournal"

    def bind_text(self, name: str, written: str) -> None:
        """Set the engine global `name` to `written`, unparsed."""
        self._engine.globalObject().setProperty(name, written)

    def push_written(self, payload: Any, *writes: str) -> dict:
        """Push `payload` after running each `writes` line against it, for
        values JSON cannot spell."""
        self.bind_json("PAYLOAD", payload)
        body = "var P = JSON.parse(PAYLOAD);" + "".join(writes)
        return self.json(
            "(function () { " + body + " return acervatorSetJournal(P); })()"
        )

    def load_skin(self) -> None:
        """Run the merged modules and push `token_payload` into the engine."""
        for path in (TOKENS_PATH, THEMES_PATH, WIDGETS_PATH, CELLS_PATH, HEADER_PATH):
            self.run(path.read_text(encoding="utf-8"))
        self.bind_json("TOKENS", token_payload())
        self.run("acervatorSetTokens(JSON.parse(TOKENS));")

    def named(self, call: str, name: Any) -> Any:
        self.bind_json("NAME", name)
        return self.json("acervatorJournal." + call + "(JSON.parse(NAME))")

    def at(self, call: str, first: Any, second: Any) -> Any:
        self.bind_json("FIRST", first)
        self.bind_json("SECOND", second)
        return self.json(
            "acervatorJournal." + call + "(JSON.parse(FIRST), JSON.parse(SECOND))"
        )


@pytest.fixture()
def js(qapp) -> JsRuntime:
    """Return a `JsRuntime` holding `MODULE_SOURCE` in a fresh engine."""
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


@pytest.fixture()
def skinned(js: JsRuntime) -> JsRuntime:
    """Return the `js` runtime after `load_skin` runs the merged modules."""
    js.load_skin()
    return js


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    declared = js.json("acervatorJournal.declaredNames()")
    missing = sorted(set(payload) - set(declared))
    assert not missing, f"{len(missing)} published fields are undeclared: {missing}"
    extra = sorted(set(declared) - set(payload))
    assert not extra, f"the module declares fields the surface has none of: {extra}"
    assert len(declared) == len(payload)
    differing = {
        name: (payload[name], js.named("field", name))
        for name in declared
        if js.named("field", name) != payload[name]
    }
    assert not differing, (
        f"{state}: {len(differing)} of {len(payload)} published fields "
        f"differ: {sorted(differing)}"
    )


def test_the_whole_payload_check_names_a_field_only_the_surface_holds(js: JsRuntime):
    payload = dict(bridge_payload())
    payload["one_the_module_never_declared"] = []
    js.push(payload)
    declared = js.json("acervatorJournal.declaredNames()")
    assert sorted(set(payload) - set(declared)) == ["one_the_module_never_declared"]


def test_the_whole_payload_check_names_a_field_only_the_module_declares(js: JsRuntime):
    payload = dict(bridge_payload())
    dropped = payload.pop("journal_table")
    assert dropped is not None
    js.push(payload)
    declared = js.json("acervatorJournal.declaredNames()")
    assert sorted(set(declared) - set(payload)) == ["journal_table"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    report = js.push(payload)
    table = payload["journal_table"]
    assert report["declared"]["fields"] == report["held"]["fields"] == len(payload)
    assert report["declared"]["rows"] == report["held"]["rows"] == len(table["rows"])
    assert report["declared"]["columns"] == report["held"]["columns"]
    assert report["held"]["columns"] == len(table["columns"])
    assert report["declared"]["entries"] == payload["entry_count"]
    assert report["held"]["lines"] == len(payload["detail_view"]["rows"])


def test_the_count_check_reports_a_payload_promising_more_rows_than_it_carries(
    js: JsRuntime,
):
    payload = state_payload("three")
    rows = payload["journal_table"]["rows"]
    payload["journal_table"]["row_count"] = len(rows) + len(rows)
    report = js.push(payload)
    assert report["declared"]["rows"] != report["held"]["rows"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_raises_no_fault_on_a_payload_the_surface_produced(
    js: JsRuntime, state: str
):
    report = js.push(state_payload(state))
    assert report["faults"] == [], f"{state}: {report['faults']}"


def test_the_module_writes_no_number():
    assert not MODULE_LITERALS["numbers"], (
        "journal_tab.js holds numeric literals: " f"{MODULE_LITERALS['numbers']}"
    )


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"journal_tab.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_tab_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & PAINTED_VALUES)
    assert not written, f"journal_tab.js spells out tab values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"journal_tab.js spells out token values: {written}"


def test_every_published_value_the_module_writes_names_a_slot_or_the_method():
    assert NAMED_VALUE in set(MODULE_LITERALS["strings"])
    written = set(MODULE_LITERALS["strings"]) & PUBLISHED_VALUES
    painted = sorted(written - NAMING_VALUES)
    assert not painted, f"the module writes the painted values {painted}"


def test_the_painted_set_still_holds_every_caption_and_colour_the_tab_shows():
    """The painted set is not empty, so the check above measures something."""
    payload = state_payload("selected")
    for shown in (
        payload["journal_group"]["title"],
        payload["recon_button"]["text"],
        payload["stats_label"]["text"],
        payload["colors"]["accent"],
        payload["formats"]["label_gap"],
        payload["formats"]["label_suffix"],
        payload["detail_view"]["rows"][0]["value"],
    ):
        assert shown in PAINTED_VALUES, shown


def test_the_module_names_only_the_surface_key_names_it_must_read(js: JsRuntime):
    js.push(bridge_payload())
    allowed = set(js.json("acervatorJournal.declaredNames()")) | NAMED_SUB_KEYS
    written = set(MODULE_LITERALS["strings"]) & PUBLISHED_KEYS
    assert not written - allowed, f"the module names {sorted(written - allowed)} more"
    assert (
        not NAMED_SUB_KEYS - written
    ), f"the list allows {sorted(NAMED_SUB_KEYS - written)} the module never writes"


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        "journal_tab.js holds a slash outside a comment, which the "
        f"literal scan cannot read: {MODULE_LITERALS['slashes']}"
    )


def test_the_alignment_map_covers_exactly_the_word_the_surface_publishes(
    js: JsRuntime,
):
    payload = state_payload("three")
    js.push(payload)
    words = js.json("acervatorJournal.alignmentWords()")
    assert words == [payload["journal_table"]["cell_alignment"]]


SPELLED_OUT_LINES = {
    "colour": 'var spelled = "' + jts.ACCENT_COLOR + '";',
    "token_value": 'var spelled = "' + str(dss.PRIMARY) + '";',
    "group_title": 'var spelled = "' + jts.JOURNAL_GROUP_TITLE + '";',
    "button_text": 'var spelled = "' + jts.RECON_BUTTON_TEXT + '";',
    "label_gap": 'var spelled = "' + jts.DETAIL_LABEL_GAP + '";',
    "label_suffix": 'var spelled = "' + jts.DETAIL_LABEL_SUFFIX + '";',
    "vote_join": 'var spelled = "' + jts.VOTE_JOIN + '";',
    "vote_indent": 'var spelled = "' + jts.VOTE_INDENT + '";',
    "detail_join": 'var spelled = "' + jts.DETAIL_JOIN + '";',
    "font_family": 'var spelled = "' + jts.DETAIL_FONT_FAMILY + '";',
    "number": "var spelled = 12;",
    "regex": "var spelled = /ab+c/;",
}


def caught_by_scan(source: str) -> set:
    """Which of the five checks above report on ``source``."""
    found = js_literals(source)
    strings = set(found["strings"])
    caught = set()
    if found["numbers"]:
        caught.add("number")
    if HEX_COLOUR.findall(source):
        caught.add("colour")
    if strings & PAINTED_VALUES:
        caught.add("painted_value")
    if strings & TOKEN_VALUES:
        caught.add("token_value")
    if found["slashes"]:
        caught.add("regex")
    return caught


@pytest.mark.parametrize("kind", sorted(SPELLED_OUT_LINES))
def test_the_literal_scan_names_a_line_that_spells_a_value_out(kind: str):
    caught = caught_by_scan(SPELLED_OUT_LINES[kind])
    assert caught, f"the scan reported nothing on the {kind} line"


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    found = js_literals("// " + jts.ACCENT_COLOR + '\nvar kept = "kept";')
    assert found["strings"] == ["kept"]
    assert not found["numbers"]


def test_each_spelled_out_value_is_caught_in_the_module_file_itself():
    original = read_module().encode("utf-8")
    before = hashlib.sha256(original).hexdigest()
    caught_each = {}
    hashes = {}
    try:
        for kind in sorted(SPELLED_OUT_LINES):
            swap_module(MODULE_PATH, original + SPELLED_OUT_LINES[kind].encode("utf-8"))
            caught_each[kind] = caught_by_scan(MODULE_PATH.read_text(encoding="utf-8"))
            swap_module(MODULE_PATH, original)
            hashes[kind] = hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()
    finally:
        swap_module(MODULE_PATH, original)
    unrestored = sorted(kind for kind, found in hashes.items() if found != before)
    assert not unrestored, f"the file was not restored after these lines: {unrestored}"
    unseen = sorted(kind for kind, caught in caught_each.items() if not caught)
    assert not unseen, f"the scan saw nothing on these lines in the file: {unseen}"
    assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before


def test_the_module_read_takes_only_a_file_that_ends_whole():
    assert read_module().rstrip().endswith(MODULE_TAIL)
    for kind, written in sorted(SPELLED_OUT_LINES.items()):
        changed = MODULE_SOURCE + written
        assert not changed.rstrip().endswith(MODULE_TAIL), kind


def test_the_changed_file_is_still_a_module_the_page_can_run(js: JsRuntime):
    for kind, written in sorted(SPELLED_OUT_LINES.items()):
        runtime = JsRuntime(js.engine_of(), MODULE_SOURCE + written)
        assert runtime.json("typeof acervatorSetJournal") == "function", kind


def python_kinds(payload: dict) -> dict:
    """The JavaScript type of every value of ``payload``, by dotted path."""
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
    payload = state_payload(state)
    js.push(payload)
    wanted = python_kinds(payload)
    found = js.json("acervatorJournal.kinds()")
    differing = {
        path: (kind, found.get(path))
        for path, kind in wanted.items()
        if found.get(path) != kind
    }
    assert not differing, f"{state}: {len(differing)} values changed type: {differing}"
    assert len(found) == len(wanted)


def test_the_type_check_names_a_value_that_changed_shape(js: JsRuntime):
    payload = state_payload("three")
    wanted = python_kinds(payload)
    payload["journal_table"]["rows"][0][2] = 12.5
    js.push(payload)
    found = js.json("acervatorJournal.kinds()")
    differing = [path for path, kind in wanted.items() if found.get(path) != kind]
    assert differing == ["journal_table.rows.0.2"], differing


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_table_cell_of_every_state_agrees_with_the_surface(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    differing = {}
    for at, row in enumerate(payload["journal_table"]["rows"]):
        for column, found in enumerate(row):
            held = js.at("cellAt", at, column)
            if held != found:
                differing[f"{at}.{column}"] = (found, held)
    assert not differing, f"{state}: {len(differing)} cells differ: {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_detail_line_of_every_state_agrees_with_the_surface(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    published_lines = payload["detail_view"]["rows"]
    assert js.json("acervatorJournal.lines()") == published_lines, state
    for at, one in enumerate(published_lines):
        assert js.named("line", at) == one, f"{state}: line {at}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_row_colour_of_every_state_agrees_with_the_surface(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    for at, found in enumerate(payload["journal_table"]["row_colors"]):
        assert js.named("rowColors", at) == found, f"{state}: row {at}"


def test_the_cell_check_names_a_column_the_module_read_from_the_wrong_place(
    js: JsRuntime,
):
    payload = state_payload("three")
    js.push(payload)
    assert js.at("cellAt", 0, 0) != js.at("cellAt", 0, 2)


def test_a_reader_returns_nothing_for_an_inherited_javascript_name(js: JsRuntime):
    js.push(state_payload("three"))
    for name in ("constructor", "toString", "hasOwnProperty", "__proto__"):
        assert js.named("field", name) is None, name
        assert js.named("action", name) is None, name
        assert js.named("colourNamed", name) is None, name
        assert js.named("skin", name) is None, name
        assert js.named("defaultText", name) is None, name


def test_the_inherited_name_check_still_reads_a_real_field(js: JsRuntime):
    payload = state_payload("three")
    js.push(payload)
    signal = sorted(payload["actions"])[0]
    assert js.named("field", "entry_count") == payload["entry_count"]
    assert js.named("action", signal) == payload["actions"][signal]
    assert js.named("colourNamed", "accent") == payload["colors"]["accent"]
    assert js.named("skin", "recon_button") == payload["skin"]["recon_button"]


#: STYLE_NAMES lists every computed property read off a drawn part.
STYLE_NAMES = [
    "color",
    "backgroundColor",
    "fontSize",
    "fontWeight",
    "fontFamily",
    "textAlign",
    "whiteSpace",
    "userSelect",
    "cursor",
    "height",
    "width",
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "borderTopStyle",
    "borderTopWidth",
    "borderTopColor",
    "borderTopLeftRadius",
]

#: EXPANDED maps a Qt shorthand to the properties it settles into.
EXPANDED = {
    "border": ("borderTopStyle", "borderTopWidth", "borderTopColor"),
    "border-radius": ("borderTopLeftRadius",),
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
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = " + json.dumps(str(HOST_WIDTH_PX) + "px") + ";"
    "window.HOST.style.height = " + json.dumps(str(HOST_HEIGHT_PX) + "px") + ";"
    "document.body.appendChild(window.HOST);"
    "window.readStyle = function (el, names) {"
    "  var computed = getComputedStyle(el);"
    "  var found = {};"
    "  names.forEach(function (n) { found[n] = computed[n]; });"
    "  return found; };"
    "window.probeStyle = function (tag, cssText, names) {"
    "  var probe = document.createElement(tag);"
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
    "        disabled: el.disabled === true, text: own,"
    "        whole: el.textContent,"
    "        style: window.readStyle(el, names) });"
    "    }"
    "    Array.prototype.slice.call(el.children).forEach(function (child) {"
    "      walk(child, here); });"
    "  };"
    "  if (window.HOST.firstChild) { walk(window.HOST.firstChild, ''); }"
    "  return JSON.stringify(found); })()"
)


class Browser:
    """The real renderer page, loaded from disk in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        self._view.resize(*VIEW_SIZE_PX)
        for attempt in range(PAGE_LOAD_ATTEMPTS):
            self.load_page()
            if self.module_ready():
                return
            assert attempt + 1 < PAGE_LOAD_ATTEMPTS, (
                "the page never defined the journal module: readyState "
                + str(self.js("document.readyState"))
                + ", scripts "
                + str(self.js("document.scripts.length"))
                + ", cells "
                + str(self.js("typeof window.acervatorSetCells"))
                + ", header "
                + str(self.js("typeof window.acervatorSetHeader"))
            )

    def load_page(self) -> None:
        """Load `INDEX_HTML` from disk and wait for Chromium to finish."""
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

    def module_ready(self) -> bool:
        """Whether the page defines `acervatorSetJournal` within the spin."""
        for _ in range(READY_ROUNDS):
            if self.js("typeof window.acervatorSetJournal") == "function":
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
    """The page, or a skip when Chromium is not installed with Qt."""
    assert qapp is not None
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    page = Browser()
    yield page
    page.close()


def give_tokens(browser: Browser) -> int:
    """Push `token_payload` into the page and apply it, since a disk-loaded
    view has no bridge."""
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    written = browser.parsed(
        "(function () {"
        "  acervatorSetTokens(JSON.parse(window.TOKENS));"
        "  return acervatorTokens.apply(document.documentElement); })()"
    )
    assert written, "no design token reached the page's stylesheet"
    return len(written)


def draw_tab(browser: Browser, payload: dict) -> list:
    """Render `payload` into `window.HOST` and return what `READ_PARTS` finds."""
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetJournal(JSON.parse(window.PAYLOAD));"
        "acervatorJournal.renderTab(window.HOST);"
    )
    return json.loads(browser.js(READ_PARTS))


def read_parts(browser: Browser) -> list:
    """Return what `READ_PARTS` finds, without rendering again."""
    return json.loads(browser.js(READ_PARTS))


def declarations_of(sheet: Any) -> list:
    """Return each property and value of `sheet`'s base block, read in
    Python rather than through the module."""
    found: list = []
    if not isinstance(sheet, str):
        return found
    body = sheet
    if "{" in sheet:
        blocks = [one for one in sheet.split("}") if "{" in one]
        base = [one for one in blocks if ":" not in one.split("{")[0]]
        body = ";".join(one.split("{", 1)[1] for one in base)
    for one in body.split(";"):
        parts = one.split(":")
        prop = parts.pop(0).strip()
        if not parts or not prop:
            continue
        value = ":".join(parts).strip()
        if value:
            found.append((prop, value))
    return found


def base_body(sheet: Any) -> str:
    return ";".join(prop + ":" + value for prop, value in declarations_of(sheet))


def probe(browser: Browser, tag: str, body: str) -> dict:
    """Return the computed values a bare `tag` takes from `body`."""
    names: list = []
    for prop, _ in declarations_of(body):
        names.extend(EXPANDED.get(prop, (prop,)))
    if not names:
        return {}
    return browser.parsed(
        "window.probeStyle("
        + json.dumps(tag)
        + ", "
        + json.dumps(body)
        + ", "
        + json.dumps(sorted(set(names)))
        + ")"
    )


def parts_at(parts: list, part: str) -> list:
    return [one for one in parts if one["attrs"].get("data-part") == part]


def slotted(parts: list, part: str, slot: str) -> dict:
    found = [
        one for one in parts_at(parts, part) if one["attrs"].get("data-slot") == slot
    ]
    assert len(found) == 1, f"{len(found)} parts named {part}/{slot}"
    return found[0]


def grouped_rows(parts: list) -> list:
    """Group each drawn row with the cells drawn after it, in document order."""
    found: list = []
    for one in parts:
        part = one["attrs"].get("data-part")
        if part == "row":
            found.append({"row": one, "cells": []})
            continue
        if part == "cell" and found:
            found[-1]["cells"].append(one)
    return found


def drawn_rows(parts: list) -> list:
    return [one["row"] for one in grouped_rows(parts)]


def drawn_cells(parts: list, at: int) -> list:
    return grouped_rows(parts)[at]["cells"]


def row_identity(parts: list) -> list:
    """Each drawn row's position beside the text of every cell it draws."""
    return [
        {
            "at": one["row"]["attrs"].get("data-row"),
            "texts": [cell["text"] for cell in one["cells"]],
        }
        for one in grouped_rows(parts)
    ]


def surface_rows(payload: dict) -> list:
    """Each published table row as position and cell texts."""
    return [
        {"at": str(at), "texts": [str(cell) for cell in row]}
        for at, row in enumerate(payload["journal_table"]["rows"])
    ]


def line_identity(parts: list) -> list:
    """Each drawn detail line's position beside its label and its value."""
    found = []
    for one in parts_at(parts, "detail-line"):
        at = one["attrs"]["data-line"]
        labels = [
            other["text"]
            for other in parts_at(parts, "detail-label")
            if other["attrs"]["data-line"] == at
        ]
        values = [
            other["text"]
            for other in parts_at(parts, "detail-value")
            if other["attrs"]["data-line"] == at
        ]
        found.append(
            {"at": at, "label": labels, "value": values, "whole": one["whole"]}
        )
    return found


def surface_lines(payload: dict) -> list:
    """Each published detail line as position, label, value and whole text."""
    found = []
    for at, line in enumerate(payload["detail_view"]["rows"]):
        labels = [line["label"]] if line["label"] else []
        found.append(
            {
                "at": str(at),
                "label": labels,
                "value": [str(line["value"])],
                "whole": line["indent"]
                + line["label"]
                + line["gap"]
                + str(line["value"]),
            }
        )
    return found


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorJournal") == "object"
    assert browser.js("typeof window.acervatorSetJournal") == "function"
    assert browser.js("typeof window.acervatorLoadJournal") == "function"


def test_the_ready_spin_reports_a_page_that_defines_no_module(browser: Browser):
    """The reload above would rubber-stamp a broken page without this."""
    assert browser.module_ready() is True
    browser.js("delete window.acervatorSetJournal;")
    assert browser.module_ready() is False
    browser.load_page()
    assert browser.module_ready() is True


def test_the_module_makes_no_network_call_of_its_own(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    draw_tab(browser, state_payload("selected"))
    browser.settle(SETTLE_MS)
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_network_check_names_a_refused_connection(browser: Browser):
    browser.js(
        WATCH_VIOLATIONS + "window.PROBE = 'pending';"
        "fetch('https://example.invalid/x')"
        "  .then(function () { window.PROBE = 'allowed'; })"
        "  .catch(function (e) { window.PROBE = 'refused: ' + e.name; });"
    )
    browser.settle(NETWORK_SETTLE_MS)
    assert browser.js("window.PROBE") == "refused: TypeError"
    violations = browser.parsed("window.VIOLATIONS")
    assert any(v.startswith("connect-src") for v in violations), violations


def test_the_drawn_table_shows_every_column_the_surface_published(browser: Browser):
    payload = state_payload("three")
    parts = draw_tab(browser, payload)
    columns = parts_at(parts, "column")
    assert [one["text"] for one in columns] == payload["journal_table"]["columns"]
    assert len(columns) == payload["journal_table"]["column_count"]


def test_the_drawn_table_shows_every_cell_the_surface_published(browser: Browser):
    payload = state_payload("three")
    parts = draw_tab(browser, payload)
    assert row_identity(parts) == surface_rows(payload)


def test_the_drawn_cell_check_names_one_changed_cell(browser: Browser):
    payload = state_payload("three")
    before = row_identity(draw_tab(browser, payload))
    payload["journal_table"]["rows"][0][2] = "changed-symbol"
    after = row_identity(draw_tab(browser, payload))
    assert before != after
    assert "changed-symbol" in after[0]["texts"]


def test_the_drawn_header_shows_the_two_filters_and_their_labels(browser: Browser):
    payload = state_payload("filtered")
    parts = draw_tab(browser, payload)
    for slot in ("bot_filter", "period_filter"):
        drawn = slotted(parts, "filter", slot)
        assert drawn["attrs"]["data-index"] == str(payload[slot]["index"])
        signal = slot + ".currentIndexChanged"
        assert drawn["attrs"]["data-action"] == payload["actions"][signal]
    for slot in ("bot_label", "period_label"):
        assert slotted(parts, "label", slot)["text"] == payload[slot]["text"]
    drawn = [
        one["attrs"].get("data-slot")
        for one in parts
        if one["path"].startswith("tab/header/")
    ]
    assert drawn == payload["header_order"]


def test_the_drawn_filter_holds_every_item_the_surface_published(browser: Browser):
    payload = state_payload("filtered")
    draw_tab(browser, payload)
    for slot in ("bot_filter", "period_filter"):
        drawn = browser.parsed(
            "Array.prototype.slice.call("
            "  window.HOST.querySelectorAll("
            + json.dumps("[data-slot='" + slot + "'] option")
            + ")"
            ").map(function (o) {"
            "  return [o.textContent, o.getAttribute('data-item-data')]; })"
        )
        wanted = [[str(one[0]), str(one[1])] for one in payload[slot]["items"]]
        assert drawn == wanted, slot


def test_the_drawn_recovery_pane_shows_its_lines_and_buttons_in_order(
    browser: Browser,
):
    payload = state_payload("recovered")
    parts = draw_tab(browser, payload)
    drawn = [
        one["attrs"].get("data-slot")
        for one in parts
        if one["attrs"].get("data-part") in ("label", "button-row", "stretch")
        and one["path"].startswith("tab/splitter")
    ]
    assert drawn == payload["recovery_order"]
    buttons = parts_at(parts, "button")
    assert [one["attrs"]["data-slot"] for one in buttons] == payload["button_row_order"]
    assert [one["text"] for one in buttons] == [
        payload[slot]["text"] for slot in payload["button_row_order"]
    ]


def test_every_drawn_child_a_check_reads_carries_a_name(browser: Browser):
    parts = draw_tab(browser, state_payload("selected"))
    unnamed = [
        one["path"]
        for one in parts
        if not any(
            key in one["attrs"]
            for key in (
                "data-slot",
                "data-row",
                "data-column",
                "data-line",
                "data-index",
                "aria-label",
            )
        )
    ]
    assert not unnamed, f"{len(unnamed)} drawn parts carry no name: {unnamed}"


def test_every_drawn_cell_colour_matches_a_probe_styled_from_the_surface(
    browser: Browser,
):
    payload = state_payload("three")
    parts = draw_tab(browser, payload)
    checked = 0
    differing = {}
    for at, colors in enumerate(payload["journal_table"]["row_colors"]):
        for column, one in enumerate(colors):
            if not one:
                continue
            drawn = drawn_cells(parts, at)[column]
            expected = probe(browser, "td", "color:" + one)
            checked += 1
            if drawn["style"]["color"] != expected["color"]:
                differing[f"{at}.{column}"] = (
                    expected["color"],
                    drawn["style"]["color"],
                )
    assert checked, "no published cell carried a colour, so nothing was compared"
    assert not differing, f"{len(differing)} of {checked} cell colours differ"


def test_the_drawn_group_matches_a_probe_styled_from_its_own_sheet(browser: Browser):
    payload = state_payload("three")
    parts = draw_tab(browser, payload)
    differing = {}
    for slot in ("journal_group", "detail_group", "recovery_group"):
        drawn = slotted(parts, "group", slot)
        expected = probe(browser, "div", base_body(payload[slot]["style_sheet"]))
        assert expected, slot
        for name, value in expected.items():
            if drawn["style"].get(name) != value:
                differing[slot + "." + name] = (value, drawn["style"].get(name))
    assert not differing, f"{len(differing)} group style values differ: {differing}"


def test_the_group_style_check_names_one_changed_colour(browser: Browser):
    payload = state_payload("three")
    parts = draw_tab(browser, payload)
    drawn = slotted(parts, "group", "journal_group")
    sheet = payload["journal_group"]["style_sheet"]
    expected = probe(
        browser, "div", base_body(sheet).replace(jts.ACCENT_COLOR, jts.NEGATIVE_COLOR)
    )
    assert drawn["style"]["color"] != expected["color"]


def test_the_drawn_buttons_match_a_probe_styled_from_their_own_sheets(
    browser: Browser,
):
    payload = state_payload("three")
    parts = draw_tab(browser, payload)
    differing = {}
    for slot in payload["button_row_order"]:
        drawn = slotted(parts, "button", slot)
        expected = probe(browser, "button", base_body(payload[slot]["style_sheet"]))
        assert expected, slot
        for name, value in expected.items():
            if drawn["style"].get(name) != value:
                differing[slot + "." + name] = (value, drawn["style"].get(name))
    assert not differing, f"{len(differing)} button style values differ: {differing}"


def test_the_drawn_detail_pane_matches_a_probe_styled_from_its_own_sheet(
    browser: Browser,
):
    payload = state_payload("selected")
    parts = draw_tab(browser, payload)
    drawn = slotted(parts, "detail-pane", "detail_view")
    expected = probe(browser, "div", base_body(payload["detail_view"]["style_sheet"]))
    assert expected
    for name, value in expected.items():
        assert drawn["style"].get(name) == value, name


def test_the_drawn_detail_pane_asks_for_the_published_font(browser: Browser):
    payload = state_payload("selected")
    parts = draw_tab(browser, payload)
    drawn = slotted(parts, "detail-pane", "detail_view")
    assert payload["detail_view"]["font_family"] in drawn["style"]["fontFamily"]
    expected = browser.parsed(
        "window.probeStyle('div', "
        + json.dumps(
            "font-size:" + str(payload["detail_view"]["font_point_size"]) + "pt"
        )
        + ', ["fontSize"])'
    )
    assert drawn["style"]["fontSize"] == expected["fontSize"]


def test_the_font_check_names_a_pane_asking_for_another_size(browser: Browser):
    payload = state_payload("selected")
    parts = draw_tab(browser, payload)
    drawn = slotted(parts, "detail-pane", "detail_view")
    other = payload["detail_view"]["font_point_size"] + 1
    expected = browser.parsed(
        "window.probeStyle('div', "
        + json.dumps("font-size:" + str(other) + "pt")
        + ', ["fontSize"])'
    )
    assert drawn["style"]["fontSize"] != expected["fontSize"]


def test_the_drawn_splitters_carry_the_published_orientation_and_handle(
    browser: Browser,
):
    payload = state_payload("three")
    parts = draw_tab(browser, payload)
    for slot in ("splitter", "bottom_splitter"):
        drawn = slotted(parts, "splitter", slot)
        assert drawn["attrs"]["data-orientation"] == payload[slot]["orientation"]
        assert (
            drawn["attrs"]["data-collapsible"]
            == str(payload[slot]["children_collapsible"]).lower()
        )
        assert drawn["attrs"]["data-declared-panes"] == str(
            len(payload[slot]["children"])
        )
        assert (
            drawn["attrs"]["data-held-panes"] == drawn["attrs"]["data-declared-panes"]
        )
    handles = parts_at(parts, "handle")
    assert len(handles) == 2
    wanted = browser.parsed(
        "window.probeStyle('div', "
        + json.dumps("height:" + str(payload["splitter"]["handle_width_px"]) + "px")
        + ', ["height"])'
    )
    across = [one for one in handles if one["attrs"]["data-slot"] == "splitter"][0]
    assert across["style"]["height"] == wanted["height"]


def test_the_hover_style_the_sheet_declares_is_painted_only_while_hovered(
    browser: Browser,
):
    payload = state_payload("three")
    draw_tab(browser, payload)
    slot = payload["button_row_order"][0]
    sheet = payload[slot]["style_sheet"]
    hovered = browser.parsed(
        "acervatorJournal.stateStyle(" + json.dumps(sheet) + ", ':hover')"
    )
    assert hovered, "the published sheet declares no hover state"
    resting = read_parts(browser)
    before = slotted(resting, "button", slot)
    browser.js(
        "window.HOST.querySelector(\"[data-slot='" + slot + "'][data-part='button']\")"
        ".dispatchEvent(new MouseEvent('mouseover', {bubbles: true}));"
    )
    browser.settle(SETTLE_MS)
    after = slotted(read_parts(browser), "button", slot)
    assert before["attrs"]["data-hovered"] == "false"
    assert after["attrs"]["data-hovered"] == "true"
    assert after["style"]["backgroundColor"] != before["style"]["backgroundColor"]


def test_the_hovered_button_matches_a_probe_styled_from_the_hover_rule(
    browser: Browser,
):
    payload = state_payload("three")
    draw_tab(browser, payload)
    slot = payload["button_row_order"][0]
    sheet = payload[slot]["style_sheet"]
    hover_body = sheet.split(":hover")[1].split("{")[1].split("}")[0]
    browser.js(
        "window.HOST.querySelector(\"[data-slot='" + slot + "'][data-part='button']\")"
        ".dispatchEvent(new MouseEvent('mouseover', {bubbles: true}));"
    )
    browser.settle(SETTLE_MS)
    drawn = slotted(read_parts(browser), "button", slot)
    expected = probe(browser, "button", base_body(hover_body))
    assert expected
    for name, value in expected.items():
        assert drawn["style"].get(name) == value, name


def changed_paths(before: list, after: list) -> set:
    """Every (part, property) whose computed value moved between reads."""
    assert len(before) == len(after), "the tab drew a different number of parts"
    moved = set()
    for at, one in enumerate(before):
        other = after[at]
        assert one["path"] == other["path"]
        for key, value in one["style"].items():
            if other["style"].get(key) != value:
                moved.add((at, key))
    return moved


def test_the_drawn_tab_follows_a_colour_token_and_nothing_else_moves(
    browser: Browser,
):
    payload = state_payload("selected")
    before = draw_tab(browser, payload)
    carried = payload["colors"]["positive"]
    name = browser.parsed("acervatorJournal.variableFor(" + json.dumps(carried) + ")")
    assert name, f"no single token carries {carried}"
    browser.js(
        "document.documentElement.style.setProperty("
        + json.dumps("--" + name)
        + ", "
        + json.dumps(str(dss.ERROR))
        + ");"
    )
    after = read_parts(browser)
    moved = changed_paths(before, after)
    assert moved, "the token moved nothing at all"
    assert {key for _, key in moved} <= {
        "color",
        "borderTopColor",
    }, f"an unset border colour is currentColor, so only these move: {moved}"
    wanted = {
        at
        for at, one in enumerate(before)
        if one["style"].get("color")
        and one["attrs"].get("data-part") in ("cell", "detail-value")
    }
    assert {at for at, _ in moved} <= wanted


def test_the_token_check_reports_nothing_when_no_token_is_rewritten(
    browser: Browser,
):
    before = draw_tab(browser, state_payload("selected"))
    assert changed_paths(before, read_parts(browser)) == set()


MARKUP_REASON = "<b>bold</b> and <img src=x onerror=alert(1)>"


def test_the_detail_pane_shows_markup_the_operator_wrote_as_text(browser: Browser):
    payload = bridge_payload(
        {
            "statistics": STATISTICS,
            "entries": [entry(reason=MARKUP_REASON)],
            "selected_row": 0,
        }
    )
    parts = draw_tab(browser, payload)
    values = [one["text"] for one in parts_at(parts, "detail-value")]
    assert MARKUP_REASON in values, values
    assert browser.parsed("window.HOST.querySelectorAll('b').length") == 0
    assert browser.parsed("window.HOST.querySelectorAll('img').length") == 0


def test_the_markup_check_reads_a_real_bold_element_when_one_is_there(
    browser: Browser,
):
    """A real bold element is found, so the markup check above measures something."""
    payload = bridge_payload(
        {
            "statistics": STATISTICS,
            "entries": [entry(reason=MARKUP_REASON)],
            "selected_row": 0,
        }
    )
    draw_tab(browser, payload)
    assert browser.parsed("window.HOST.querySelectorAll('b').length") == 0
    browser.js("window.HOST.insertAdjacentHTML('beforeend', '<b>real</b>');")
    assert browser.parsed("window.HOST.querySelectorAll('b').length") == 1


def test_the_detail_pane_keeps_the_indent_the_surface_published(browser: Browser):
    payload = state_payload("voted")
    parts = draw_tab(browser, payload)
    indented = [line for line in payload["detail_view"]["rows"] if line["indent"]]
    assert indented, "no published line carried an indent"
    drawn = parts_at(parts, "detail-line")
    assert len(drawn) == len(payload["detail_view"]["rows"])
    for at, line in enumerate(payload["detail_view"]["rows"]):
        assert drawn[at]["whole"].startswith(line["indent"]), at
    pane = slotted(parts, "detail-pane", "detail_view")
    assert pane["style"]["whiteSpace"] == "pre-wrap"


def test_the_drawn_rows_keep_the_order_the_surface_published(browser: Browser):
    payload = state_payload("three")
    parts = draw_tab(browser, payload)
    drawn = [one["attrs"]["data-row"] for one in drawn_rows(parts)]
    assert drawn == [str(at) for at, _ in enumerate(payload["journal_table"]["rows"])]
    texts = [one["texts"] for one in row_identity(parts)]
    assert len(set(map(tuple, texts))) == len(texts), "the rows were not distinct"


def test_the_row_order_check_names_a_reordered_list(browser: Browser):
    payload = state_payload("three")
    before = row_identity(draw_tab(browser, payload))
    payload["journal_table"]["rows"] = list(reversed(payload["journal_table"]["rows"]))
    payload["journal_table"]["row_colors"] = list(
        reversed(payload["journal_table"]["row_colors"])
    )
    after = row_identity(draw_tab(browser, payload))
    assert after != before
    assert [one["texts"] for one in after] == list(
        reversed([one["texts"] for one in before])
    )


def test_the_row_identity_check_names_two_rows_swapped(browser: Browser):
    payload = state_payload("three")
    before = row_identity(draw_tab(browser, payload))
    rows = payload["journal_table"]["rows"]
    rows[0], rows[1] = rows[1], rows[0]
    after = row_identity(draw_tab(browser, payload))
    assert after != before, "swapping two rows changed nothing"
    assert after[0]["texts"] == before[1]["texts"]
    assert after[1]["texts"] == before[0]["texts"]


def test_the_drawn_detail_lines_keep_the_order_the_surface_published(
    browser: Browser,
):
    payload = state_payload("voted")
    parts = draw_tab(browser, payload)
    assert line_identity(parts) == surface_lines(payload)


def test_the_line_order_check_names_a_reordered_pane(browser: Browser):
    payload = state_payload("voted")
    before = line_identity(draw_tab(browser, payload))
    payload["detail_view"]["rows"] = list(reversed(payload["detail_view"]["rows"]))
    after = line_identity(draw_tab(browser, payload))
    assert after != before
    assert [one["whole"] for one in after] == list(
        reversed([one["whole"] for one in before])
    )


def test_the_line_identity_check_names_two_lines_values_swapped(browser: Browser):
    payload = state_payload("voted")
    before = line_identity(draw_tab(browser, payload))
    lines = payload["detail_view"]["rows"]
    first, second = lines[1]["value"], lines[2]["value"]
    assert first != second, "the two lines carried the same value"
    lines[1]["value"], lines[2]["value"] = second, first
    after = line_identity(draw_tab(browser, payload))
    assert after != before, "swapping two lines' values changed nothing"
    assert after[1]["value"] == before[2]["value"]
    assert after[2]["value"] == before[1]["value"]
    assert after[1]["label"] == before[1]["label"], "the labels moved too"


def test_the_line_identity_check_names_a_value_moved_under_another_label(
    browser: Browser,
):
    payload = state_payload("voted")
    before = line_identity(draw_tab(browser, payload))
    lines = payload["detail_view"]["rows"]
    lines[1]["label"] = lines[2]["label"]
    after = line_identity(draw_tab(browser, payload))
    assert after != before
    assert after[1]["label"] == before[2]["label"]
    assert after[1]["value"] == before[1]["value"]


#: Values JSON carries unchanged, written into one detail line's value.
HOSTILE_VALUES = {
    "a true flag": True,
    "nothing at all": None,
    "an empty text": "",
    "a two hundred character word": "X" * 200,
    "a text carrying a newline": "first\nsecond",
    "markup": "<script>alert(1)</script>",
    "a number where text belongs": 1.0,
    "a very large integer": 10**24,
}

#: Each number JSON cannot spell, an infinity among them, written in after.
HOSTILE_NUMBERS = {
    "not a number": "NaN",
    "an infinity": "Infinity",
    "a negative infinity": "-Infinity",
}


def same_value(shown: Any, sent: Any) -> bool:
    """Whether `shown` is `sent`, an integer past the double range apart."""
    if type(sent) is int:
        return float(shown) == float(sent)
    return shown == sent


@pytest.mark.parametrize("case", sorted(HOSTILE_VALUES))
def test_the_tab_holds_whatever_line_value_the_surface_produced(
    js: JsRuntime, case: str
):
    payload = state_payload("selected")
    payload["detail_view"]["rows"][3]["value"] = HOSTILE_VALUES[case]
    js.push(payload)
    shown = js.named("line", 3)["value"]
    assert same_value(shown, HOSTILE_VALUES[case]), f"{case}: the tab holds {shown!r}"


@pytest.mark.parametrize("case", sorted(HOSTILE_VALUES))
def test_the_tab_holds_whatever_cell_text_the_surface_produced(
    js: JsRuntime, case: str
):
    payload = state_payload("three")
    payload["journal_table"]["rows"][0][2] = HOSTILE_VALUES[case]
    js.push(payload)
    shown = js.at("cellAt", 0, 2)
    assert same_value(shown, HOSTILE_VALUES[case]), f"{case}: the tab holds {shown!r}"


def test_the_value_comparison_names_a_value_the_tab_changed(js: JsRuntime):
    """same_value refuses a changed word and a changed number."""
    assert not same_value("other", HOSTILE_VALUES["a two hundred character word"])
    assert not same_value(2.0, HOSTILE_VALUES["a very large integer"])


@pytest.mark.parametrize("case", sorted(HOSTILE_VALUES))
def test_one_bad_line_costs_the_other_lines_nothing(browser: Browser, case: str):
    payload = state_payload("selected")
    whole = line_identity(draw_tab(browser, payload))
    payload["detail_view"]["rows"][3]["value"] = HOSTILE_VALUES[case]
    spoilt = line_identity(draw_tab(browser, payload))
    assert len(spoilt) == len(whole), f"{case}: the pane lost lines"
    assert spoilt[0] == whole[0], f"{case}: the first line changed"
    assert spoilt[4] == whole[4], f"{case}: the fifth line changed"


def test_the_neighbour_check_names_a_line_that_did_change(browser: Browser):
    payload = state_payload("selected")
    whole = line_identity(draw_tab(browser, payload))
    payload["detail_view"]["rows"][0]["value"] = "changed-neighbour"
    spoilt = line_identity(draw_tab(browser, payload))
    assert spoilt[0] != whole[0]


@pytest.mark.parametrize("case", sorted(HOSTILE_NUMBERS))
def test_the_tab_holds_a_number_json_cannot_spell(js: JsRuntime, case: str):
    payload = state_payload("selected")
    js.push_written(
        payload, "P.detail_view.rows[3].value = " + HOSTILE_NUMBERS[case] + ";"
    )
    shown = js.named("line", 3)["value"]
    assert shown is None or isinstance(shown, float), f"{case}: {shown!r}"


#: The five entry fields the surface carries into the payload unformatted.
UNFORMATTED_FIELDS = ("symbol", "action", "side", "ta_direction", "ta_timeframe")


@pytest.mark.parametrize("name", UNFORMATTED_FIELDS)
def test_the_bridge_cannot_carry_a_not_a_number_this_surface_can_emit(
    js: JsRuntime, name: str
):
    """Issue #257 reaches this surface through `view_model`."""
    payload = jts.view_model(
        {
            "reset": True,
            "statistics": STATISTICS,
            "entries": [entry(**{name: float("nan")})],
            "selected_row": 0,
        }
    )
    written = json.dumps(payload)
    assert "NaN" in written, name
    js.bind_text("BROKEN", written)
    result = js.run(
        "(function () { try { JSON.parse(BROKEN); return 'parsed'; }"
        " catch (e) { return e.name; } })()"
    )
    assert result.toString() == "SyntaxError"


def test_the_bridge_check_parses_the_same_payload_without_the_bad_value(
    js: JsRuntime,
):
    written = json.dumps(state_payload("selected"))
    assert "NaN" not in written and "Infinity" not in written
    js.bind_text("WHOLE", written)
    result = js.run(
        "(function () { try { JSON.parse(WHOLE); return 'parsed'; }"
        " catch (e) { return e.name; } })()"
    )
    assert result.toString() == "parsed"


@pytest.mark.parametrize("name", sorted(jts.view_model({"reset": True})))
def test_a_field_the_payload_omits_is_named_as_missing(js: JsRuntime, name: str):
    payload = state_payload("three")
    del payload[name]
    report = js.push(payload)
    assert {
        "where": None,
        "field": name,
        "fault": "missing",
        "detail": None,
    } in report["faults"]
    assert report["held"]["fields"] == report["declared"]["fields"] - 1


#: NULLABLE_NAMES holds the top-level fields the surface itself publishes
#: as nothing, which cannot be wrongly null.
NULLABLE_NAMES = sorted(
    name for name, value in jts.view_model({"reset": True}).items() if value is None
)
FILLED_NAMES = sorted(set(jts.view_model({"reset": True})) - set(NULLABLE_NAMES))


def test_the_nullable_names_are_exactly_the_fields_the_surface_leaves_empty(
    js: JsRuntime,
):
    js.push(state_payload("three"))
    assert sorted(js.json("acervatorJournal.nullableNames()")) == NULLABLE_NAMES
    assert NULLABLE_NAMES, "the surface published no empty field at all"


@pytest.mark.parametrize("name", FILLED_NAMES)
def test_a_field_carrying_null_is_named(js: JsRuntime, name: str):
    payload = state_payload("three")
    payload[name] = None
    report = js.push(payload)
    assert {
        "where": None,
        "field": name,
        "fault": "null",
        "detail": None,
    } in report["faults"]


@pytest.mark.parametrize("name", NULLABLE_NAMES)
def test_a_field_the_surface_leaves_empty_is_not_named_as_null(
    js: JsRuntime, name: str
):
    report = js.push(state_payload("three"))
    assert [one for one in report["faults"] if one["field"] == name] == []


def test_the_missing_field_check_is_quiet_on_a_whole_payload(js: JsRuntime):
    report = js.push(state_payload("three"))
    kinds = [one["fault"] for one in report["faults"]]
    assert "missing" not in kinds
    assert "null" not in kinds


#: HELD_TYPES names each wrong type the surface publishes a default for.
HELD_TYPES = {
    "a cell text that is a number": (
        ["journal_table", "rows", 0, 2],
        12.5,
        "row:0/cell:2",
        "text",
    ),
    "a line value that is a number": (
        ["detail_view", "rows", 3, "value"],
        12.5,
        "line:3",
        "value",
    ),
    "a line label that is a number": (
        ["detail_view", "rows", 3, "label"],
        7,
        "line:3",
        "label",
    ),
    "a line indent that is a number": (
        ["detail_view", "rows", 3, "indent"],
        2,
        "line:3",
        "indent",
    ),
    "a line gap that is a number": (
        ["detail_view", "rows", 3, "gap"],
        1,
        "line:3",
        "gap",
    ),
    "a line weight that is text": (
        ["detail_view", "rows", 3, "bold"],
        "true",
        "line:3",
        "bold",
    ),
}


def put(payload: dict, path: list, value: Any) -> None:
    node: Any = payload
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value


@pytest.mark.parametrize("case", sorted(HELD_TYPES))
def test_a_wrong_type_is_named_where_the_surface_publishes_a_default(
    js: JsRuntime, case: str
):
    path, value, where, name = HELD_TYPES[case]
    payload = state_payload("selected")
    put(payload, path, value)
    report = js.push(payload)
    named = [
        one
        for one in report["faults"]
        if one["fault"] == "wrong-type" and one["where"] == where
    ]
    assert named and named[0]["field"] == name, f"{case}: {report['faults']}"


def test_the_wrong_type_check_is_quiet_on_a_whole_payload(js: JsRuntime):
    report = js.push(state_payload("voted"))
    assert [one for one in report["faults"] if one["fault"] == "wrong-type"] == []


def test_a_colour_field_with_no_published_default_is_not_type_checked(
    js: JsRuntime,
):
    """The two colour fields carry null, so nothing measures their type."""
    payload = state_payload("selected")
    assert payload["detail_view"]["line_defaults"]["label_color"] is None
    assert payload["detail_view"]["line_defaults"]["value_color"] is None
    payload["detail_view"]["rows"][3]["label_color"] = 7
    report = js.push(payload)
    assert [
        one
        for one in report["faults"]
        if one["fault"] == "wrong-type" and one["field"] == "label_color"
    ] == []


def test_a_row_that_is_not_a_list_is_named(js: JsRuntime):
    payload = state_payload("three")
    payload["journal_table"]["rows"][0] = "not a row"
    report = js.push(payload)
    assert {
        "where": "row:0",
        "field": None,
        "fault": "not-an-object",
        "detail": "string",
    } in report["faults"]


def test_a_detail_line_that_is_not_an_object_is_named(js: JsRuntime):
    payload = state_payload("selected")
    payload["detail_view"]["rows"][3] = "not a line"
    report = js.push(payload)
    assert {
        "where": "line:3",
        "field": None,
        "fault": "not-an-object",
        "detail": "string",
    } in report["faults"]


def test_a_slot_no_field_answers_is_named(js: JsRuntime):
    payload = state_payload("three")
    payload["recovery_order"] = payload["recovery_order"] + ["never_a_field"]
    report = js.push(payload)
    assert {
        "where": "recovery_order",
        "field": "never_a_field",
        "fault": "unslotted",
        "detail": None,
    } in report["faults"]


def test_the_slot_check_is_quiet_on_every_published_order(js: JsRuntime):
    report = js.push(state_payload("three"))
    assert [one for one in report["faults"] if one["fault"] == "unslotted"] == []


def test_a_payload_that_is_not_an_object_leaves_the_module_unloaded(js: JsRuntime):
    js.push(state_payload("three"))
    report = js.push([])
    assert js.json("acervatorJournal.isLoaded()") is False
    assert report["declared"] is None
    assert js.json("acervatorJournal.rows()") == []


def test_a_hostile_payload_still_draws_a_tab(browser: Browser):
    payload = state_payload("selected")
    for name in ("colors", "actions", "skin", "labels", "titles"):
        payload[name] = None
    parts = draw_tab(browser, payload)
    assert len(drawn_rows(parts)) == len(payload["journal_table"]["rows"])
    assert row_identity(parts) == surface_rows(payload)
    assert len(parts_at(parts, "detail-line")) == len(payload["detail_view"]["rows"])


def test_no_sheet_the_surface_publishes_carries_a_colour_qt_reads_apart(
    skinned: JsRuntime,
):
    report = skinned.push(state_payload("three"))
    named = [
        one for one in report["faults"] if one["fault"] in ("qt-colour", "not-css")
    ]
    assert named == [], f"the tab publishes a sheet CSS reads apart: {named}"


def test_the_qt_colour_check_names_an_eight_digit_hex(skinned: JsRuntime):
    payload = state_payload("three")
    payload["skin"]["recon_button"] = "color: " + jts.ACCENT_COLOR + "ff;"
    report = skinned.push(payload)
    assert {
        "where": "skin",
        "field": "recon_button",
        "fault": "qt-colour",
        "detail": "color",
    } in report["faults"]


def test_the_qt_colour_check_names_a_byte_alpha_rgba(skinned: JsRuntime):
    payload = state_payload("three")
    payload["skin"]["recon_button"] = "color: rgba(0,0,0,128);"
    report = skinned.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "qt-colour"]
    assert len(named) == 1 and named[0]["field"] == "recon_button"


def test_the_qt_colour_check_keeps_a_fraction_alpha_rgba(skinned: JsRuntime):
    payload = state_payload("three")
    payload["skin"]["recon_button"] = "color: rgba(0,0,0,0.5);"
    report = skinned.push(payload)
    assert [one for one in report["faults"] if one["fault"] == "qt-colour"] == []


def test_the_qt_only_check_names_an_added_gradient(skinned: JsRuntime):
    payload = state_payload("three")
    payload["skin"]["recon_button"] = "background: qlineargradient(x1:0, y1:0);"
    report = skinned.push(payload)
    assert {
        "where": "skin",
        "field": "recon_button",
        "fault": "not-css",
        "detail": "background",
    } in report["faults"]


def test_the_refused_declaration_never_reaches_the_drawn_style(skinned: JsRuntime):
    sheet = "color: " + jts.ACCENT_COLOR + "ff; font-weight: bold;"
    skinned.bind_json("SHEET", sheet)
    style = skinned.json("acervatorJournal.styleOf(JSON.parse(SHEET))")
    assert "color" not in style
    assert style["fontWeight"] == "bold"


def test_the_refusal_keeps_a_six_digit_hex(skinned: JsRuntime):
    sheet = "color: " + jts.ACCENT_COLOR + "; font-weight: bold;"
    skinned.bind_json("SHEET", sheet)
    style = skinned.json("acervatorJournal.styleOf(JSON.parse(SHEET))")
    assert "color" in style
    assert style["fontWeight"] == "bold"


FAKE_BRIDGE = (
    "window.CALLS = [];"
    "window.acervator = { call: function (method, params) {"
    "  window.CALLS.push([method, params]);"
    "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
)

REFUSING_BRIDGE = (
    "window.REFUSALS = 0;"
    "window.acervator = { call: function () {"
    "  window.REFUSALS = window.REFUSALS + 1;"
    "  return Promise.reject(new Error('refused')); } };"
)


def test_the_module_asks_the_backend_for_the_surface_method(js: JsRuntime):
    payload = state_payload("three")
    js.bind_json("PAYLOAD", payload)
    js.run(FAKE_BRIDGE)
    js.run("acervatorLoadJournal();")
    drain_events()
    assert js.json("window.CALLS") == [[jts.METHOD, {}]]
    assert js.json("acervatorJournal.isLoaded()") is True


def test_a_second_ask_costs_no_second_round_trip(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload("three"))
    js.run(FAKE_BRIDGE)
    js.run("acervatorLoadJournal(); acervatorLoadJournal();")
    drain_events()
    assert len(js.json("window.CALLS")) == 1


def test_the_ask_counter_reports_a_second_round_trip(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload("three"))
    js.run(FAKE_BRIDGE)
    js.run("acervatorLoadJournal();")
    drain_events()
    js.run("acervatorJournal.forget(); acervatorLoadJournal();")
    drain_events()
    assert len(js.json("window.CALLS")) == 2


def test_a_refused_first_ask_is_not_remembered(js: JsRuntime):
    js.run(REFUSING_BRIDGE)
    js.run("acervatorLoadJournal();")
    drain_events()
    assert js.json("acervatorJournal.loadError()") == "refused"
    js.run("acervatorLoadJournal();")
    drain_events()
    assert js.json("window.REFUSALS") == 2


def test_the_module_reports_a_missing_bridge_rather_than_raising(js: JsRuntime):
    js.run("acervatorLoadJournal();")
    drain_events()
    assert js.json("acervatorJournal.loadError()") == (
        "the preload bridge is not present"
    )


def test_the_page_names_the_journal_module_among_its_assets():
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    named = [ref for ref in refs if ref.endswith("journal_tab.js")]
    assert named, "index.html names no journal module"
    assert (INDEX_HTML.parent / named[0]).resolve() == MODULE_PATH.resolve()


def test_the_page_loads_the_journal_module_after_the_modules_it_uses():
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    at = [i for i, ref in enumerate(refs) if ref.endswith("journal_tab.js")][0]
    for needed in ("table_cells.js", "header_strip.js", "react.production.min.js"):
        before = [i for i, ref in enumerate(refs) if ref.endswith(needed)]
        assert before and before[0] < at, needed + " is not loaded first"


def test_the_module_reuses_the_cell_and_sheet_rules_rather_than_copying_them(
    skinned: JsRuntime,
):
    payload = state_payload("three")
    skinned.push(payload)
    carried = payload["colors"]["positive"]
    skinned.bind_json("VALUE", carried)
    mine = skinned.json("acervatorJournal.colour(JSON.parse(VALUE))")
    theirs = skinned.json("acervatorCells.colour(JSON.parse(VALUE))")
    assert mine == theirs and mine != carried, f"{mine} against {theirs}"
    sheet = payload["recovery_group"]["style_sheet"]
    skinned.bind_json("SHEET", sheet)
    assert skinned.json("acervatorJournal.styleOf(JSON.parse(SHEET))") == skinned.json(
        "acervatorHeader.styleOf(JSON.parse(SHEET))"
    )


def test_the_resolver_answers_the_plain_value_with_the_cell_module_absent(
    js: JsRuntime,
):
    carried = jts.POSITIVE_COLOR
    js.bind_json("VALUE", carried)
    assert js.json("acervatorJournal.colour(JSON.parse(VALUE))") == carried
    assert js.json("acervatorJournal.variableFor(JSON.parse(VALUE))") is None
