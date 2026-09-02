"""Drives `market_inspector_topologies.js` against its Qt-free surface."""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import market_inspector_topologies_surface as mts
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    new_engine,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "market_inspector_topologies.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"
NEIGHBOURS = ("design_tokens.js", "shared_widgets.js", "header_strip.js")

MODULE_TAIL = "})(window);"
MODULE_READ_ATTEMPTS = 200
MODULE_READ_PAUSE_S = 0.01

LOCK_PATH = Path(tempfile.gettempdir()) / (
    "acervator_topologies_js_"
    + hashlib.sha256(str(MODULE_PATH).encode("utf-8")).hexdigest()[:16]
    + ".lock"
)
LOCK_WAIT_S = 120.0
LOCK_POLL_S = 0.02


@contextlib.contextmanager
def module_file_held():
    """Blocks while LOCK_PATH exists, so only one caller writes MODULE_PATH."""
    start = time.monotonic()
    while True:
        try:
            LOCK_PATH.mkdir()
            break
        except (FileExistsError, PermissionError):
            # Windows raises PermissionError for a directory mid-delete.
            waited = time.monotonic() - start
            assert waited < LOCK_WAIT_S, f"{LOCK_PATH} was never released"
            time.sleep(LOCK_POLL_S)
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            LOCK_PATH.rmdir()


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
MODULE_BYTES = MODULE_PATH.read_bytes()

JS_TIMEOUT_MS = 30_000
SETTLE_MS = 500
NETWORK_SETTLE_MS = 1500
READY_ROUNDS = 100
READY_STEP_MS = 100
LOAD_ATTEMPTS = 3
VIEW_SIZE_PX = (1100, 800)
HOST_WIDTH_PX = 900
HOST_HEIGHT_PX = 700

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

NOW = 1700000000.0
LATER = NOW + 600.0

BOTS = [
    {
        "asset": "BTC",
        "role": "hub",
        "symbol": "BTC/USD",
        "existing_bot_id": "b1",
        "suggested_target_usd": 100.0,
    },
    {
        "asset": "ETH",
        "role": "spoke",
        "symbol": "ETH/USD",
        "existing_bot_id": "",
        "suggested_target_usd": 250.0,
    },
    {
        "asset": "SOL",
        "role": "spoke",
        "symbol": "SOL/USD",
        "existing_bot_id": "",
        "suggested_target_usd": 1250.0,
    },
]

WIRES = [
    {
        "source_asset": "BTC",
        "target_asset": "ETH",
        "pct": 25.0,
        "rationale": "Sector L1: hub BTC feeds spoke ETH",
    },
    {
        "source_asset": "BTC",
        "target_asset": "SOL",
        "pct": 25.0,
        "rationale": "Sector L1: hub BTC feeds spoke SOL",
    },
]


def proposal(held: str, score: float = 90.0, title: str = "") -> dict:
    """One sector-cluster proposal, its hub wired to both spokes."""
    return {
        "id": held,
        "archetype": "sector_cluster",
        "title": title or ("Sector cluster: " + held),
        "score": score,
        "assets": ["BTC", "ETH", "SOL"],
        "bots": list(BOTS),
        "wires": list(WIRES),
        "adopt_notes": ["hub BTC wires 25.0% to each of 2 spoke(s)."],
    }


#: SENT_IDS is the order the pane suppresses in, numeric so a bag renumbers.
SENT_IDS = ("7", "3", "1")
THREE = [proposal(SENT_IDS[0], 90.0), proposal(SENT_IDS[1], 60.0)]
THREE.append(proposal(SENT_IDS[2], 10.0))

STATES = (
    "unwired",
    "ready",
    "listed",
    "empty",
    "error",
    "dismissed",
    "preview",
    "adopted",
)


def drive(name: str) -> mts.TopologiesPaneModel:
    """The surface's pane, driven into one named state."""
    model = mts.TopologiesPaneModel(NOW)
    if name == "unwired":
        return model
    if name == "error":
        model.set_proposal_source(mts.ProposalSource(raises=RuntimeError("no feed")))
        model.refresh()
        return model
    model.set_dismiss_store(mts.DismissStore(holds={}))
    model.set_proposal_source(
        mts.ProposalSource(list(THREE) if name != "empty" else [])
    )
    if name == "ready":
        return model
    model.refresh()
    if name in ("listed", "empty"):
        return model
    if name == "dismissed":
        for held in SENT_IDS:
            model.on_dismiss(held)
        return model
    model.on_preview(SENT_IDS[0])
    if name == "preview":
        return model
    model.adopt_from(model.previews[-1])
    return model


def state_payload(name: str) -> dict:
    """One named state as the bridge would hand it over."""
    return json.loads(json.dumps(mts.build_view_model(drive(name))))


def token_payload() -> dict:
    return json.loads(json.dumps(dss.build_view_model()))


class JsRuntime(JsEngine):
    """The module in a QJSEngine, its neighbour modules loaded first."""

    module_path = MODULE_PATH
    setter = "acervatorSetTopologies"

    def named(self, name: str, *args: Any) -> Any:
        """Call one exported function with JSON arguments."""
        self.bind_json("ARGS", list(args))
        return self.json(
            "acervatorTopologies." + name + ".apply(null, JSON.parse(ARGS))"
        )


def module_bodies() -> str:
    """The neighbour modules and this one, as one script."""
    parts = [(WEB / name).read_text(encoding="utf-8") for name in NEIGHBOURS]
    with module_file_held():
        parts.append(read_module())
    return "\n".join(parts)


@pytest.fixture()
def js(qapp) -> JsRuntime:
    assert qapp is not None
    engine = JsRuntime(new_engine(), module_bodies())
    engine.bind_json("TOKENS", token_payload())
    engine.run("acervatorSetTokens(JSON.parse(TOKENS))")
    return engine


# --- whole payload, both directions, every state ----------------------


@pytest.mark.parametrize("name", STATES)
def test_every_state_reaches_the_module_value_for_value(name: str, js: JsRuntime):
    payload = state_payload(name)
    js.push(payload)
    assert js.json("acervatorTopologies.payload()") == payload


@pytest.mark.parametrize("name", STATES)
def test_every_state_declares_and_holds_the_same_counts(name: str, js: JsRuntime):
    answer = js.push(state_payload(name))
    assert answer["declared"] == answer["held"], answer


@pytest.mark.parametrize("name", STATES)
def test_no_state_raises_a_fault_of_any_kind(name: str, js: JsRuntime):
    answer = js.push(state_payload(name))
    assert answer["faults"] == [], answer["faults"]


def test_the_count_check_reads_a_field_taken_off_the_payload(js: JsRuntime):
    payload = state_payload("preview")
    del payload["cards"]
    del payload["warnings"]
    answer = js.push(payload)
    assert answer["held"]["fields"] == answer["declared"]["fields"] - 2
    assert [one["fault"] for one in answer["faults"]].count("missing") == 2


def test_the_value_check_reads_one_changed_status_line(js: JsRuntime):
    payload = state_payload("listed")
    payload["status_text"] = "MOVED"
    js.push(payload)
    assert js.json("acervatorTopologies.field('status_text')") == "MOVED"


def test_the_cell_counts_read_a_row_taken_out_of_the_preview(js: JsRuntime):
    payload = state_payload("preview")
    payload["previews"][0]["bot_rows"].pop()
    answer = js.push(payload)
    assert answer["held"]["botCells"] == answer["declared"]["botCells"]
    assert answer["held"]["botCells"] == len(mts.BOTS_COLUMNS) * 2


# --- both sides agree by value and by type ----------------------------


def python_kinds(value: Any, prefix: str = "") -> dict:
    """Every dotted path of `value` and the JavaScript type it becomes."""
    found: dict = {}
    if isinstance(value, dict):
        walk = value.items()
    elif isinstance(value, list):
        walk = ((str(at), one) for at, one in enumerate(value))
    else:
        return found
    for name, inner in walk:
        path = (prefix + "." + str(name)) if prefix else str(name)
        found[path] = JS_TYPE_OF[type(inner).__name__]
        found.update(python_kinds(inner, path))
    return found


@pytest.mark.parametrize("name", STATES)
def test_every_state_agrees_on_the_type_of_every_value(name: str, js: JsRuntime):
    payload = state_payload(name)
    js.push(payload)
    assert js.json("acervatorTopologies.kinds()") == python_kinds(payload)


def test_the_type_check_reads_a_number_written_where_words_belong(js: JsRuntime):
    payload = state_payload("ready")
    payload["pane"]["refresh_text"] = len(mts.REFRESH_TEXT)
    js.push(payload)
    assert js.json("acervatorTopologies.kinds()")["pane.refresh_text"] == "number"


# --- no value literal in the module -----------------------------------


def surface_values() -> set:
    """Every value the surface owns, less the method name it is called by."""
    found = {
        str(value)
        for name, value in vars(mts).items()
        if name.isupper() and isinstance(value, (str, int, float))
        if not isinstance(value, bool)
    }
    for table in (mts.ARCHETYPE_LABELS, mts.LOG_LEVELS, mts.ACTIONS, mts.TIMERS):
        found.update(str(value) for value in table.values())
    found.discard("")
    return found - {mts.METHOD}


def literal_findings(source: str) -> dict:
    """Every kind of written-in value the module must not carry."""
    found = js_literals(source)
    return {
        "numbers": found["numbers"],
        "slashes": found["slashes"],
        "colours": HEX_COLOUR.findall(source),
        "surface_values": sorted(set(found["strings"]) & surface_values()),
        "token_values": sorted(
            set(found["strings"]) & {str(one) for one in dss.TOKENS.values()}
        ),
    }


def test_the_shipped_module_file_carries_no_literal_of_any_kind():
    found = literal_findings(MODULE_SOURCE)
    assert not any(found.values()), f"the clean module reported: {found}"


#: One line per kind, written over MODULE_PATH and then taken back off.
PLANTED_LINES = {
    "colour": 'var written = "' + mts.SCORE_HIGH_COLOR + '";',
    "number": "var written = " + str(mts.DISMISS_TTL_SECONDS) + ";",
    "format": 'var written = "' + mts.STATUS_COUNT_FORMAT + '";',
    "word": 'var written = "' + mts.BOT_STATUS_EXISTING + '";',
    "tag": 'var written = "' + mts.STRONG_OPEN + '";',
    "token": 'var written = "' + str(dss.TOKENS["RADIUS_CARD"]) + '";',
    "regex": "var written = /ab+c/;",
}

PLANTED_KINDS = {
    "colour": ("colours", "surface_values"),
    "number": ("numbers",),
    "format": ("surface_values",),
    "word": ("surface_values",),
    "tag": ("surface_values",),
    "token": ("token_values",),
    "regex": ("slashes",),
}


@pytest.mark.parametrize("kind", sorted(PLANTED_LINES))
def test_the_literal_scan_names_a_value_written_into_the_module_file(kind: str):
    with module_file_held():
        before = MODULE_BYTES
        digest = hashlib.sha256(before).hexdigest()
        written = before + ("\n" + PLANTED_LINES[kind] + "\n").encode("utf-8")
        try:
            swap_module(MODULE_PATH, written)
            found = literal_findings(MODULE_PATH.read_text(encoding="utf-8"))
            named = {one for one in PLANTED_KINDS[kind] if found[one]}
            assert named == set(PLANTED_KINDS[kind]), f"the scan missed {kind}: {found}"
        finally:
            swap_module(MODULE_PATH, before)
        assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == digest


# --- order and identity by name ---------------------------------------


def test_the_dismissal_bag_loses_its_order_and_the_published_list_keeps_it(
    js: JsRuntime,
):
    payload = state_payload("dismissed")
    assert list(payload["dismissal"]["held"]) == list(SENT_IDS)
    js.push(payload)
    keys = js.json("Object.keys(acervatorTopologies.payload().dismissal.held)")
    assert keys != list(SENT_IDS), "the bag kept its order, so the list proves nothing"
    assert js.json("acervatorTopologies.dismissedOrder()") == list(SENT_IDS)


def test_each_write_through_the_store_carries_its_own_order_as_a_list(js: JsRuntime):
    payload = state_payload("dismissed")
    js.push(payload)
    orders = js.json("acervatorTopologies.persistedOrder()")
    assert orders == [list(SENT_IDS[:1]), list(SENT_IDS[:2]), list(SENT_IDS)]
    for at, written in enumerate(orders):
        keys = js.json(
            "Object.keys(acervatorTopologies.payload().persisted[" + str(at) + "][1])"
        )
        assert sorted(keys) == sorted(written)


def test_a_card_is_read_by_its_proposal_id_and_not_by_its_position(js: JsRuntime):
    payload = state_payload("listed")
    js.push(payload)
    assert js.json("acervatorTopologies.cardOrder()") == list(SENT_IDS)
    for at, held in enumerate(SENT_IDS):
        assert js.named("cardByName", held) == payload["cards"][at]


def test_a_card_read_by_a_name_no_proposal_carries_answers_with_nothing(
    js: JsRuntime,
):
    js.push(state_payload("listed"))
    assert js.named("cardByName", "nobody") is None


def test_a_bot_row_is_read_by_its_asset_and_carries_every_column(js: JsRuntime):
    payload = state_payload("preview")
    js.push(payload)
    assert js.named("botOrder", 0) == ["BTC", "ETH", "SOL"]
    row = js.named("botRow", 0, "SOL")
    assert row == dict(zip(mts.BOTS_COLUMNS, payload["previews"][0]["bot_rows"][2]))


def test_a_wire_row_needs_both_ends_because_the_source_repeats(js: JsRuntime):
    payload = state_payload("preview")
    js.push(payload)
    rows = payload["previews"][0]["wire_rows"]
    sources = [js.named("rowNameOf", row, [0]) for row in rows]
    pairs = [js.named("rowNameOf", row, [0, 1]) for row in rows]
    assert len(set(sources)) == 1, f"the sources were meant to repeat: {sources}"
    assert len(set(pairs)) == len(rows), f"the pairs collided: {pairs}"
    assert js.named("wireOrder", 0) == [["BTC", "ETH"], ["BTC", "SOL"]]
    assert js.named("wireRow", 0, "BTC", "SOL") == dict(zip(mts.WIRES_COLUMNS, rows[1]))


def test_a_label_alone_is_no_identity_because_three_sit_in_both_groups(
    js: JsRuntime,
):
    js.push(state_payload("preview"))
    pairs = js.json("acervatorTopologies.labelPairs()")
    names = [one[1] for one in pairs]
    assert len(pairs) == 15, f"the pane drew {len(pairs)} labelled parts"
    assert len(set(names)) == 11, sorted(set(names))
    assert js.json("acervatorTopologies.labelCollisions()") == ["BTC", "ETH", "SOL"]


def test_the_collision_check_reports_nothing_when_no_group_repeats_a_label(
    js: JsRuntime,
):
    payload = state_payload("preview")
    payload["previews"][0]["wire_rows"] = []
    js.push(payload)
    assert js.json("acervatorTopologies.labelCollisions()") == []


def test_a_repeated_bot_asset_is_named_as_a_duplicate(js: JsRuntime):
    payload = state_payload("preview")
    rows = payload["previews"][0]["bot_rows"]
    rows[1][0] = rows[0][0]
    kinds = [one["fault"] for one in js.push(payload)["faults"]]
    assert kinds.count("duplicate-name") == 1, kinds


# --- the markup refusal -----------------------------------------------


def test_every_card_title_arrives_as_three_pieces_that_rebuild_the_label(
    js: JsRuntime,
):
    payload = state_payload("listed")
    js.push(payload)
    pieces = payload["marks"]["card_titles"]
    assert len(pieces) == len(payload["cards"])
    for entry, (lead, body, tail) in zip(payload["cards"], pieces):
        rebuilt = lead + mts.STRONG_OPEN + body + mts.STRONG_CLOSE + tail
        assert rebuilt == entry["title"], (rebuilt, entry["title"])


def test_a_title_whose_pieces_do_not_rebuild_the_label_is_named(js: JsRuntime):
    payload = state_payload("listed")
    payload["marks"]["card_titles"][0][1] = "OTHER"
    faults = js.push(payload)["faults"]
    assert [one["fault"] for one in faults] == ["mark-mismatch"], faults


@pytest.mark.parametrize("field", ["meta", "badge"])
def test_a_card_value_carrying_a_tag_is_refused_by_name(field: str, js: JsRuntime):
    payload = state_payload("listed")
    payload["cards"][0][field] = "<img src='x'>"
    faults = js.push(payload)["faults"]
    assert [one["fault"] for one in faults] == ["markup"], faults
    assert faults[0]["field"] == field


def test_a_stored_title_carrying_a_tag_still_rebuilds_and_stays_text(js: JsRuntime):
    hostile = "<img src='http://example.invalid/x.png'>"
    payload = state_payload("unwired")
    card = mts.ProposalCardModel(proposal("p1", 90.0, hostile))
    card.build()
    payload["cards"] = [
        {
            "accessible_name": mts.CARD_ACCESSIBLE_NAME,
            "title": card.title_text,
            "badge": card.badge_text,
            "badge_style": card.badge_style,
            "meta": card.meta_text,
        }
    ]
    payload["marks"]["card_titles"] = [
        mts.marked_pieces(card.title_text, mts.STRONG_OPEN, mts.STRONG_CLOSE)
    ]
    payload["screen"] = [mts.CARD_CLASS, mts.STRETCH]
    payload["proposals"] = ["p1"]
    faults = js.push(payload)["faults"]
    assert faults == [], faults
    assert hostile in js.json("acervatorTopologies.bag('marks')")["card_titles"][0][1]


# --- the colour trap --------------------------------------------------


def swapped(colour: str) -> str:
    """One six-digit colour written the way Qt reads eight digits."""
    return "#ff" + colour.lstrip("#")


@pytest.mark.parametrize("field", ["high_color", "mid_color", "low_color"])
def test_a_score_colour_written_the_qt_way_is_refused_by_name(
    field: str, js: JsRuntime
):
    payload = state_payload("ready")
    payload["score"][field] = swapped(payload["score"][field])
    faults = js.push(payload)["faults"]
    assert [one["fault"] for one in faults] == ["qt-colour"], faults
    assert faults[0]["field"] == field


def test_a_bot_colour_written_the_qt_way_is_refused_and_paints_nothing(
    js: JsRuntime,
):
    payload = state_payload("preview")
    payload["previews"][0]["bot_colors"][1][0] = swapped(mts.NEW_BOT_COLOR)
    faults = js.push(payload)["faults"]
    assert [one["fault"] for one in faults] == ["qt-colour"], faults
    assert js.named("colour", swapped(mts.NEW_BOT_COLOR)) is None


def test_the_colour_check_lets_the_six_digit_value_through(js: JsRuntime):
    js.push(state_payload("preview"))
    assert js.named("qtColour", mts.NEW_BOT_COLOR) is None
    assert js.named("colour", mts.NEW_BOT_COLOR) == mts.NEW_BOT_COLOR


def test_a_card_sheet_colour_written_the_qt_way_is_refused_by_name(js: JsRuntime):
    payload = state_payload("listed")
    payload["cards"][0]["badge_style"] = payload["cards"][0]["badge_style"].replace(
        mts.SCORE_HIGH_COLOR, swapped(mts.SCORE_HIGH_COLOR)
    )
    faults = js.push(payload)["faults"]
    assert [one["fault"] for one in faults] == ["qt-colour"], faults


# --- design tokens ----------------------------------------------------


#: Every value the pane paints with, by the field that carries it.
TOKEN_CANDIDATES = {
    "score.high_color": mts.SCORE_HIGH_COLOR,
    "score.mid_color": mts.SCORE_MID_COLOR,
    "score.low_color": mts.SCORE_LOW_COLOR,
    "dialog.new_bot_color": mts.NEW_BOT_COLOR,
    "card.spacing": mts.CARD_SPACING,
    "pane.spacing": mts.PANE_SPACING,
    "pane.scroll_spacing": mts.SCROLL_SPACING,
    "dialog.spacing": mts.DIALOG_SPACING,
    "dialog.body_spacing": mts.DIALOG_BODY_SPACING,
    "dialog.min_width": mts.DIALOG_MIN_WIDTH,
    "dialog.min_height": mts.DIALOG_MIN_HEIGHT,
}


def test_the_token_lookup_answers_for_every_value_the_pane_paints(js: JsRuntime):
    js.push(state_payload("preview"))
    refused = {}
    for field, value in TOKEN_CANDIDATES.items():
        carrier = js.named("variableFor", value)
        refused[field] = carrier
    resolved = {name: one for name, one in refused.items() if one is not None}
    assert set(refused) == set(TOKEN_CANDIDATES)
    assert len(resolved) <= len(TOKEN_CANDIDATES), resolved


def test_a_length_takes_no_token_from_a_group_that_means_another_thing(
    js: JsRuntime,
):
    js.push(state_payload("preview"))
    borrowed = {}
    for field, value in TOKEN_CANDIDATES.items():
        if isinstance(value, str):
            continue
        painted = js.named("length", value)
        if str(painted).startswith("calc("):
            borrowed[field] = painted
    assert not borrowed or all(
        js.named("variableInGroups", TOKEN_CANDIDATES[field], ["spacing"]) is not None
        for field in borrowed
    ), borrowed


# --- hostile payloads --------------------------------------------------


HOSTILE_PATHS = (
    "cards",
    "previews",
    "screen",
    "dismissal",
    "pane",
    "dialog",
    "card",
    "marks",
    "proposals",
    "persisted",
)

HOSTILE_VALUES = {
    "missing": None,
    "null": None,
    "number": 1,
    "words": "not-a-list",
    "nan": float("nan"),
    "inf": float("inf"),
    "minus_inf": float("-inf"),
    "huge": 10**24,
    "long_name": "n" * 200,
    "markup": "<img src='x'>",
    "newline": "one\ntwo",
}


def hostile_payload(path: str, kind: str) -> dict:
    """The preview state with one field made hostile."""
    payload = state_payload("preview")
    if kind == "missing":
        del payload[path]
        return payload
    value = HOSTILE_VALUES[kind]
    payload[path] = None if kind == "null" else value
    return payload


@pytest.mark.parametrize("path", HOSTILE_PATHS)
@pytest.mark.parametrize("kind", sorted(HOSTILE_VALUES))
def test_a_hostile_top_level_field_is_named_and_the_module_still_answers(
    path: str, kind: str, js: JsRuntime
):
    payload = hostile_payload(path, kind)
    if kind in ("nan", "inf", "minus_inf"):
        payload = json.loads(json.dumps(payload, allow_nan=True).replace("NaN", "null"))
        payload = json.loads(
            json.dumps(payload).replace("Infinity", "null").replace("-null", "null")
        )
    answer = js.push(payload)
    assert isinstance(answer["faults"], list)
    assert answer["faults"], f"{path} made {kind} raised nothing"
    assert js.json("acervatorTopologies.isLoaded()") is True


@pytest.mark.parametrize("kind", sorted(HOSTILE_VALUES))
def test_a_hostile_bot_row_is_walked_without_the_module_refusing(
    kind: str, js: JsRuntime
):
    payload = state_payload("preview")
    rows = payload["previews"][0]["bot_rows"]
    if kind == "missing":
        del payload["previews"][0]["bot_rows"]
    elif kind == "null":
        rows[0] = None
    elif kind in ("nan", "inf", "minus_inf", "huge", "number"):
        rows[0][0] = 1 if kind in ("number",) else 10**24
    else:
        rows[0][0] = HOSTILE_VALUES[kind]
    answer = js.push(payload)
    assert isinstance(answer["faults"], list)
    assert js.named("botOrder", 0) is not None


def test_a_wire_naming_one_node_at_both_ends_is_reported(js: JsRuntime):
    payload = state_payload("preview")
    payload["previews"][0]["wire_rows"][0][1] = payload["previews"][0]["wire_rows"][0][
        0
    ]
    kinds = [one["fault"] for one in js.push(payload)["faults"]]
    assert "self-link" in kinds, kinds


def test_a_wire_naming_a_node_the_bot_list_does_not_carry_is_reported(
    js: JsRuntime,
):
    payload = state_payload("preview")
    payload["previews"][0]["wire_rows"][0][1] = "NOBODY"
    faults = js.push(payload)["faults"]
    named = [one for one in faults if one["fault"] == "no-such-node"]
    assert [one["detail"] for one in named] == ["NOBODY"], faults


def test_the_link_checks_report_nothing_for_the_wires_the_surface_built(
    js: JsRuntime,
):
    kinds = [one["fault"] for one in js.push(state_payload("preview"))["faults"]]
    assert "self-link" not in kinds and "no-such-node" not in kinds, kinds


def test_a_screen_naming_an_element_the_module_cannot_draw_is_reported(
    js: JsRuntime,
):
    payload = state_payload("listed")
    payload["screen"][0] = "QSplitter"
    faults = js.push(payload)["faults"]
    assert faults[0]["fault"] == "unknown-element", faults
    assert faults[0]["detail"] == "QSplitter"


@pytest.mark.parametrize("kind", ["number", "words", "null"])
def test_a_scalar_standing_where_a_list_is_walked_is_named_not_stepped_into(
    kind: str, js: JsRuntime
):
    payload = state_payload("preview")
    payload["previews"] = None if kind == "null" else HOSTILE_VALUES[kind]
    faults = js.push(payload)["faults"]
    wanted = "null" if kind == "null" else "not-a-list"
    assert wanted in [one["fault"] for one in faults], faults
    assert js.json("acervatorTopologies.kinds()")["previews"] in (
        "null",
        "number",
        "string",
    )


# --- the payload carries plain data only ------------------------------


PLAIN = (str, int, float, bool, type(None))


def unplain(value: Any, prefix: str = "") -> list:
    """Every path of `value` holding something JSON cannot carry."""
    found: list = []
    if isinstance(value, dict):
        walk = list(value.items())
    elif isinstance(value, list):
        walk = [(str(at), one) for at, one in enumerate(value)]
    else:
        return [prefix] if not isinstance(value, PLAIN) else []
    for name, inner in walk:
        path = (prefix + "." + str(name)) if prefix else str(name)
        found.extend(unplain(inner, path))
    return found


@pytest.mark.parametrize("name", STATES)
def test_no_state_publishes_anything_but_plain_data(name: str):
    payload = mts.build_view_model(drive(name))
    assert unplain(payload) == [], "the pane published a live object"


def test_the_plain_data_check_names_a_live_object_put_into_the_payload():
    payload = mts.build_view_model(drive("listed"))
    payload["cards"][0]["source"] = mts.ProposalSource()
    assert unplain(payload) == ["cards.0.source"]


# --- the rendered page ------------------------------------------------


class Browser:
    """The real renderer page, loaded from disk in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        self._view.resize(*VIEW_SIZE_PX)
        for attempt in range(LOAD_ATTEMPTS):
            self.load_page()
            if self.module_ready():
                return
            assert (
                attempt + 1 < LOAD_ATTEMPTS
            ), "the page never defined the topology module: readyState " + str(
                self.js("document.readyState")
            )

    def load_page(self) -> None:
        from PySide6.QtCore import QEventLoop, QTimer, QUrl

        loop = QEventLoop()
        box: dict = {}

        def _loaded(ok: bool) -> None:
            box.setdefault("ok", ok)
            loop.quit()

        self._view.loadFinished.connect(_loaded)
        self._view.load(QUrl.fromLocalFile(str(INDEX_HTML)))
        QTimer.singleShot(JS_TIMEOUT_MS, loop.quit)
        loop.exec()
        self._view.loadFinished.disconnect(_loaded)
        assert box.get("ok") is True, f"{INDEX_HTML.name} did not load: {box}"

    def module_ready(self) -> bool:
        """Whether the page defines the setter, which loadFinished does not
        promise."""
        for _ in range(READY_ROUNDS):
            if self.js("typeof window.acervatorSetTopologies") == "function":
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


#: STYLE_NAMES lists every computed property read off a drawn part.
STYLE_NAMES = [
    "color",
    "backgroundColor",
    "display",
    "flexDirection",
    "whiteSpace",
    "overflow",
    "userSelect",
    "fontWeight",
    "fontStyle",
    "fontSize",
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "borderTopStyle",
    "borderTopWidth",
    "borderTopColor",
    "borderTopLeftRadius",
    "gap",
    "textAlign",
]

PAGE_HELPERS = (
    "window.HOST = document.getElementById('topology-host');"
    "if (!window.HOST) {"
    "  window.HOST = document.createElement('div');"
    "  window.HOST.id = 'topology-host';"
    "  document.body.appendChild(window.HOST); }"
    "window.HOST.style.width = " + json.dumps(str(HOST_WIDTH_PX) + "px") + ";"
    "window.HOST.style.height = " + json.dumps(str(HOST_HEIGHT_PX) + "px") + ";"
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
    "        text: own,"
    "        width: el.getBoundingClientRect().width,"
    "        height: el.getBoundingClientRect().height,"
    "        style: window.readStyle(el, names) });"
    "    }"
    "    Array.prototype.slice.call(el.children).forEach(function (child) {"
    "      walk(child, here); });"
    "  };"
    "  if (window.HOST.firstChild) { walk(window.HOST.firstChild, ''); }"
    "  return JSON.stringify(found); })()"
)

WATCH_VIOLATIONS = (
    "window.VIOLATIONS = [];"
    "document.addEventListener('securitypolicyviolation', function (e) {"
    "  window.VIOLATIONS.push(e.violatedDirective + ' ' + e.blockedURI); });"
)


def give_tokens(browser: Browser) -> int:
    """Push the design tokens into the page, since a disk-loaded view has no
    bridge."""
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    written = browser.parsed(
        "(function () {"
        "  acervatorSetTokens(JSON.parse(window.TOKENS));"
        "  return acervatorTokens.apply(document.documentElement); })()"
    )
    assert written, "no design token reached the page's stylesheet"
    return len(written)


def draw(browser: Browser, payload: dict, which: str = "renderPane") -> list:
    """Render `payload` into window.HOST and return what READ_PARTS finds."""
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    call = (
        "acervatorTopologies.renderPreview(window.HOST, 0)"
        if which == "renderPreview"
        else "acervatorTopologies.renderPane(window.HOST)"
    )
    browser.js("acervatorSetTopologies(JSON.parse(window.PAYLOAD));" + call + ";")
    return json.loads(browser.js(READ_PARTS))


def by_part(parts: list, name: str) -> list:
    return [one for one in parts if one["attrs"].get("data-part") == name]


def one_part(parts: list, name: str) -> dict:
    found = by_part(parts, name)
    assert len(found) == 1, f"{len(found)} parts named {name}"
    return found[0]


def probe(browser: Browser, tag: str, body: str, names: list) -> dict:
    """The computed values a bare `tag` takes from the whole declaration."""
    return browser.parsed(
        "window.probeStyle("
        + json.dumps(tag)
        + ", "
        + json.dumps(body)
        + ", "
        + json.dumps(sorted(set(names)))
        + ")"
    )


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorTopologies") == "object"
    assert browser.js("typeof window.acervatorLoadTopologies") == "function"


def test_the_module_makes_no_network_call_of_its_own(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    draw(browser, state_payload("preview"), "renderPreview")
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
    assert any(
        one.startswith("connect-src") for one in browser.parsed("window.VIOLATIONS")
    )


@pytest.mark.parametrize("name", STATES)
def test_every_element_the_page_draws_carries_a_part_name(name: str, browser: Browser):
    which = "renderPreview" if name in ("preview", "adopted") else "renderPane"
    draw(browser, state_payload(name), which)
    every = browser.js("window.HOST.querySelectorAll('*').length")
    named = browser.js("window.HOST.querySelectorAll('[data-part]').length")
    assert every == named, f"{every - named} drawn elements carry no part name"
    assert every > 0, "the page drew nothing at all"


def test_the_part_name_check_reads_one_element_left_unnamed(browser: Browser):
    draw(browser, state_payload("listed"))
    browser.js("window.HOST.firstChild.appendChild(document.createElement('span'));")
    every = browser.js("window.HOST.querySelectorAll('*').length")
    named = browser.js("window.HOST.querySelectorAll('[data-part]').length")
    assert every == named + 1


def test_the_pane_draws_one_card_for_every_proposal_the_surface_published(
    browser: Browser,
):
    payload = state_payload("listed")
    parts = draw(browser, payload)
    assert len(by_part(parts, "card")) == len(payload["cards"])
    assert [one["attrs"]["data-name"] for one in by_part(parts, "card")] == list(
        SENT_IDS
    )


def test_the_card_count_reads_a_shorter_list_as_shorter(browser: Browser):
    payload = state_payload("listed")
    payload["screen"] = payload["screen"][1:]
    payload["cards"] = payload["cards"][1:]
    payload["proposals"] = payload["proposals"][1:]
    parts = draw(browser, payload)
    assert len(by_part(parts, "card")) == 2


def test_the_empty_pane_draws_its_one_label_and_no_card(browser: Browser):
    parts = draw(browser, state_payload("empty"))
    assert one_part(parts, "empty-label")["text"] == mts.EMPTY_TEXT
    assert not by_part(parts, "card")


def test_the_status_line_and_footer_carry_the_words_the_surface_holds(
    browser: Browser,
):
    payload = state_payload("error")
    parts = draw(browser, payload)
    assert one_part(parts, "status-line")["text"] == payload["status_text"]
    assert one_part(parts, "footer")["text"] == mts.FOOTER_TEXT


def test_the_preview_draws_every_bot_and_wire_row_the_surface_published(
    browser: Browser,
):
    payload = state_payload("preview")
    parts = draw(browser, payload, "renderPreview")
    entry = payload["previews"][0]
    rows = [
        one
        for one in by_part(parts, "grid-row")
        if one["attrs"].get("data-table") == "bots"
    ]
    assert len(by_part(parts, "grid-row")) == len(entry["bot_rows"]) + len(
        entry["wire_rows"]
    )
    assert [one["attrs"]["data-name"] for one in rows] == [
        json.dumps([row[0]], separators=(",", ":")) for row in entry["bot_rows"]
    ]


def test_the_preview_row_check_reads_one_row_taken_away(browser: Browser):
    payload = state_payload("preview")
    payload["previews"][0]["wire_rows"] = payload["previews"][0]["wire_rows"][:1]
    parts = draw(browser, payload, "renderPreview")
    assert len(by_part(parts, "grid-row")) == 4


def test_every_drawn_cell_carries_the_text_the_surface_published(
    browser: Browser,
):
    payload = state_payload("preview")
    parts = draw(browser, payload, "renderPreview")
    drawn = [one["text"] for one in by_part(parts, "grid-cell")]
    wanted = [
        str(cell)
        for row in payload["previews"][0]["bot_rows"]
        + payload["previews"][0]["wire_rows"]
        for cell in row
    ]
    assert drawn == wanted


def test_a_marked_title_reaches_the_page_as_text_and_never_as_a_tag(
    browser: Browser,
):
    hostile = "<img src='http://example.invalid/x.png'>"
    payload = state_payload("listed")
    card = mts.ProposalCardModel(proposal(SENT_IDS[0], 90.0, hostile))
    card.build()
    payload["cards"][0]["title"] = card.title_text
    payload["marks"]["card_titles"][0] = mts.marked_pieces(
        card.title_text, mts.STRONG_OPEN, mts.STRONG_CLOSE
    )
    parts = draw(browser, payload)
    body = [one for one in by_part(parts, "mark-body") if hostile in one["text"]]
    assert len(body) == 1, [one["text"] for one in by_part(parts, "mark-body")]
    assert browser.js("window.HOST.querySelectorAll('img').length") == 0


def test_the_markup_measurement_shows_the_two_widths_a_tag_costs(
    browser: Browser,
):
    hostile = "<img src='http://example.invalid/x.png'>"
    measured = browser.parsed(
        "(function () {"
        "  var body = document.body;"
        "  var text = document.createElement('span');"
        "  text.style.whiteSpace = 'pre';"
        "  text.textContent = " + json.dumps(hostile) + ";"
        "  var tag = document.createElement('span');"
        "  tag.style.whiteSpace = 'pre';"
        "  tag.innerHTML = " + json.dumps(hostile) + ";"
        "  body.appendChild(text); body.appendChild(tag);"
        "  var found = [text.getBoundingClientRect().width,"
        "    tag.getBoundingClientRect().width];"
        "  text.remove(); tag.remove();"
        "  return found; })()"
    )
    assert measured[0] > measured[1], measured
    assert measured[1] < 40, f"the tag drew {measured[1]}px, so it was not parsed"


def test_the_card_frame_matches_a_probe_built_from_the_whole_declaration(
    browser: Browser,
):
    payload = state_payload("listed")
    parts = draw(browser, payload)
    card = by_part(parts, "card")[0]
    sheet = browser.parsed(
        "acervatorTopologies.keptSheet(" + json.dumps(payload["card"]["style"]) + ")"
    )
    wanted = probe(browser, "div", sheet, STYLE_NAMES)
    for name in ("borderTopStyle", "borderTopWidth", "borderTopColor"):
        assert card["style"][name] == wanted[name], (name, card["style"], wanted)


def test_the_card_frame_probe_reads_a_missing_border_as_different(
    browser: Browser,
):
    payload = state_payload("listed")
    parts = draw(browser, payload)
    card = by_part(parts, "card")[0]
    bare = probe(browser, "div", "", STYLE_NAMES)
    assert card["style"]["borderTopWidth"] != bare["borderTopWidth"]


@pytest.mark.parametrize(
    "part,bag,field",
    [
        ("status-line", "pane", "status_style"),
        ("footer", "pane", "footer_style"),
        ("card-meta", "card", "meta_style"),
        ("dismiss-button", "card", "dismiss_style"),
    ],
)
def test_a_skinned_part_matches_a_probe_styled_from_its_whole_sheet(
    part: str, bag: str, field: str, browser: Browser
):
    payload = state_payload("listed")
    parts = draw(browser, payload)
    drawn = by_part(parts, part)[0]
    sheet = browser.parsed(
        "acervatorTopologies.keptSheet(" + json.dumps(payload[bag][field]) + ")"
    )
    wanted = probe(browser, "div", sheet, STYLE_NAMES)
    assert drawn["style"]["color"] == wanted["color"], (drawn["style"], wanted)


def test_the_pane_margins_match_the_numbers_the_surface_published(
    browser: Browser,
):
    payload = state_payload("listed")
    parts = draw(browser, payload)
    pane = one_part(parts, "pane")
    measured = [
        pane["style"]["paddingLeft"],
        pane["style"]["paddingTop"],
        pane["style"]["paddingRight"],
        pane["style"]["paddingBottom"],
    ]
    assert measured == [str(one) + "px" for one in payload["pane"]["margins"]]


def test_the_card_margins_match_the_numbers_the_surface_published(
    browser: Browser,
):
    payload = state_payload("listed")
    parts = draw(browser, payload)
    body = by_part(parts, "card-body")[0]
    measured = [
        body["style"]["paddingLeft"],
        body["style"]["paddingTop"],
        body["style"]["paddingRight"],
        body["style"]["paddingBottom"],
    ]
    wanted = [str(one) + "px" for one in payload["card"]["margins"]]
    assert measured == wanted, f"the card body padded {measured}, wanted {wanted}"


def test_the_margin_check_reads_a_changed_number(browser: Browser):
    payload = state_payload("listed")
    payload["card"]["margins"] = [21, 22, 23, 24]
    parts = draw(browser, payload)
    assert by_part(parts, "card-body")[0]["style"]["paddingLeft"] == "21px"


def test_the_marked_body_takes_the_weight_the_surface_named(browser: Browser):
    payload = state_payload("listed")
    parts = draw(browser, payload)
    body = by_part(parts, "mark-body")[0]
    wanted = probe(
        browser,
        "strong",
        "font-weight: " + payload["marks"]["strong_weight"],
        STYLE_NAMES,
    )
    assert body["style"]["fontWeight"] == wanted["fontWeight"]


def test_the_summary_takes_the_slant_the_surface_named(browser: Browser):
    payload = state_payload("preview")
    parts = draw(browser, payload, "renderPreview")
    marked = [one for one in parts if one["path"].endswith("summary/mark-body")]
    assert len(marked) == 1, [one["path"] for one in parts]
    body = marked[0]["style"]["fontStyle"]
    wanted = probe(
        browser, "em", "font-style: " + payload["marks"]["emphasis_slant"], STYLE_NAMES
    )
    assert body == wanted["fontStyle"]


def paint_counts(browser: Browser, name: str) -> dict:
    """What one drawn state asks the page to paint, counted on this host."""
    which = "renderPreview" if name in ("preview", "adopted") else "renderPane"
    parts = draw(browser, state_payload(name), which)
    return {
        "parts": len(parts),
        "fills": len(
            [
                one
                for one in parts
                if one["style"]["backgroundColor"] != "rgba(0, 0, 0, 0)"
            ]
        ),
        "axis_lines": len(
            [one for one in parts if one["style"]["borderTopWidth"] != "0px"]
        ),
        "corner_arcs": len(
            [
                one
                for one in parts
                if one["style"]["borderTopLeftRadius"] not in ("0px", "")
            ]
        ),
        "texts": len([one for one in parts if one["text"]]),
        "canvas": browser.js("window.HOST.querySelectorAll('canvas').length"),
        "svg": browser.js("window.HOST.querySelectorAll('svg').length"),
    }


@pytest.mark.parametrize("name", STATES)
def test_every_state_draws_only_what_a_css_box_can_draw(name: str, browser: Browser):
    counted = paint_counts(browser, name)
    assert counted["parts"] > 0, counted
    assert counted["canvas"] == 0, counted
    assert counted["svg"] == 0, counted


def test_the_paint_count_reads_a_state_that_draws_more_than_another(browser: Browser):
    listed = paint_counts(browser, "listed")
    empty = paint_counts(browser, "empty")
    assert listed["parts"] > empty["parts"], (listed, empty)
    assert listed["fills"] > empty["fills"], (listed, empty)


def test_the_bridge_load_reports_when_no_preload_is_present(browser: Browser):
    answer = browser.parsed(
        "(function () { acervatorTopologies.forget();"
        "  var bridge = window.acervator; window.acervator = undefined;"
        "  acervatorLoadTopologies({});"
        "  window.acervator = bridge;"
        "  return acervatorTopologies.loadError(); })()"
    )
    assert answer == "the preload bridge is not present"


def test_the_module_names_the_slot_the_market_inspector_left_for_it(js: JsRuntime):
    js.push(state_payload("listed"))
    assert js.json("acervatorTopologies.slots()") == ["market-inspector-topologies"]
    assert js.json("acervatorTopologies.method()") == mts.METHOD


def test_the_pane_carries_that_slot_name_on_the_element_it_draws(browser: Browser):
    parts = draw(browser, state_payload("listed"))
    assert one_part(parts, "pane")["attrs"]["data-slot"] == (
        "market-inspector-topologies"
    )


def test_the_module_answers_nothing_when_it_is_handed_something_that_is_not_a_bag(
    js: JsRuntime,
):
    answer = js.push([mts.METHOD])
    assert answer["declared"] is None
    assert answer["faults"][0]["fault"] == "not-an-object"
    assert js.json("acervatorTopologies.payload()") == {}


def test_the_module_file_is_named_in_the_page_the_renderer_loads():
    text = INDEX_HTML.read_text(encoding="utf-8")
    assert MODULE_PATH.name in text
    for neighbour in NEIGHBOURS:
        assert text.index(neighbour) < text.index(MODULE_PATH.name), neighbour


def test_the_module_parses_as_plain_javascript(qapp):
    assert qapp is not None
    engine = new_engine()
    engine.evaluate("var window = this;")
    answer = engine.evaluate(MODULE_SOURCE, MODULE_PATH.name)
    assert not answer.isError(), answer.toString()


def test_every_expiry_arrives_as_the_second_the_pane_wrote(js: JsRuntime):
    payload = state_payload("dismissed")
    js.push(payload)
    held = js.json("acervatorTopologies.payload()")["dismissal"]["held"]
    assert set(held) == set(payload["dismissal"]["held"])
    assert not math.isnan(sum(held.values()))
    assert set(held.values()) == {NOW + mts.DISMISS_TTL_SECONDS}


def test_the_pane_carries_every_call_the_surface_recorded(js: JsRuntime):
    payload = state_payload("dismissed")
    js.push(payload)
    assert js.json("acervatorTopologies.calls()") == payload["calls"]
    assert js.json("acervatorTopologies.callNames()") == payload["call_names"]


def test_the_warning_lines_reach_the_module_in_the_order_they_were_written(
    js: JsRuntime,
):
    payload = state_payload("error")
    js.push(payload)
    assert js.json("acervatorTopologies.warnings()") == payload["warnings"]
    assert payload["warnings"][0][0] == mts.LEVEL_ERROR


def test_the_archetype_and_action_bags_keep_their_order_across_the_bridge(
    js: JsRuntime,
):
    payload = state_payload("listed")
    js.push(payload)
    for name in ("archetypes", "actions", "timers"):
        assert js.json("Object.keys(acervatorTopologies." + name + "())") == list(
            payload[name]
        ), name


def test_the_order_check_reads_a_bag_whose_keys_come_back_renumbered(js: JsRuntime):
    payload = state_payload("dismissed")
    js.push(payload)
    keys = js.json("Object.keys(acervatorTopologies.payload().dismissal.held)")
    assert keys == sorted(SENT_IDS), keys
    assert keys != list(SENT_IDS)


def test_a_cache_order_shorter_than_the_bag_is_reported(js: JsRuntime):
    payload = state_payload("dismissed")
    payload["dismissal"]["order"] = payload["dismissal"]["order"][:1]
    faults = js.push(payload)["faults"]
    assert [one["fault"] for one in faults] == ["lost-order"], faults


def test_an_order_naming_an_id_the_bag_does_not_hold_is_reported(js: JsRuntime):
    payload = state_payload("dismissed")
    payload["dismissal"]["order"][0] = "nobody"
    faults = js.push(payload)["faults"]
    assert [one["fault"] for one in faults] == ["missing"], faults
    assert faults[0]["detail"] == "nobody"
