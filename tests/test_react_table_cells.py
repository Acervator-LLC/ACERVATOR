"""Checks table_cells.js against the table_cells_surface payload it draws."""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
import sys
import tempfile
import time
import types
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import table_cells_surface as tcs
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
MODULE_PATH = WEB / "table_cells.js"
TOKENS_PATH = WEB / "design_tokens.js"
THEMES_PATH = WEB / "theme_engine.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 2

#: Python type name -> the typeof acervatorCells.types reports for it.
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

#: Named for MODULE_PATH, so two worktrees do not wait on each other.
LOCK_PATH = Path(tempfile.gettempdir()) / (
    "acervator_table_cells_js_"
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
            # Windows raises PermissionError for a directory that is mid-delete.
            waited = time.monotonic() - start
            assert waited < LOCK_WAIT_S, f"{LOCK_PATH} was never released"
            time.sleep(LOCK_POLL_S)
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            LOCK_PATH.rmdir()


def module_text() -> str:
    """Reads MODULE_PATH while holding LOCK_PATH."""
    with module_file_held():
        return MODULE_PATH.read_text(encoding="utf-8")


AMMO_CELL = tcs.AMMO_CELL
BTC_CELL = tcs.TARGET_BTC_CELL
ETH_CELL = tcs.TARGET_ETH_CELL


def bridge_payload(**params: Any) -> dict:
    """Returns tcs.view_model(params) after the json.dumps desktop_bridge applies."""
    params.setdefault("reset", True)
    return json.loads(json.dumps(tcs.view_model(params), ensure_ascii=True))


def token_payload() -> dict:
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


def theme_payload() -> dict:
    return json.loads(json.dumps(tes.view_model({}), ensure_ascii=True))


class FakeRates:
    """Holds btc_usd and eth_usd for CurrencyRateMonitor.snapshot."""

    def __init__(self, btc_usd: float, eth_usd: float) -> None:
        self.btc_usd = btc_usd
        self.eth_usd = eth_usd


class FakeMonitor:
    def __init__(self, rates: FakeRates, error: Exception | None = None) -> None:
        self.rates = rates
        self.error = error

    def snapshot(self) -> FakeRates:
        if self.error is not None:
            raise self.error
        return self.rates


class FakePair:
    """Holds the pct_24h that _priced_denom reads."""

    def __init__(self, pct_24h: float) -> None:
        self.pct_24h = pct_24h


class FakeScout:
    """Answers get_pair from pairs and appends every call to asked."""

    def __init__(self, pairs: dict | None = None, error: Exception | None = None):
        self.pairs = dict(pairs or {})
        self.error = error
        self.asked: list = []

    def get_pair(self, base, quote, exchange_id=None):
        self.asked.append((base, quote, exchange_id))
        if self.error is not None:
            raise self.error
        return self.pairs.get((base, quote))


def install_market(monkeypatch, spec: dict) -> FakeScout:
    """Puts FakeMonitor and FakeScout into sys.modules, and returns the FakeScout."""
    rates = FakeRates(spec.get("btc_usd", 60000.0), spec.get("eth_usd", 3000.0))
    monitor = FakeMonitor(rates, spec.get("monitor_error"))
    scout = FakeScout(spec.get("pairs"), spec.get("scout_error"))
    rate_module = types.ModuleType("src.exchange.currency_rate_monitor")
    rate_module.get_currency_monitor = lambda: monitor
    scout_module = types.ModuleType("src.exchange.market_pairs_scout")
    scout_module.get_scout = lambda: scout
    monkeypatch.setitem(sys.modules, "src.exchange.currency_rate_monitor", rate_module)
    monkeypatch.setitem(sys.modules, "src.exchange.market_pairs_scout", scout_module)
    return scout


PAIRS_UP = {
    ("RAVE", "BTC"): FakePair(3.5),
    ("RAVE", "ETH"): FakePair(-2.5),
    ("RAVE", "USD"): FakePair(1.0),
}
PAIRS_FLAT = {("RAVE", "BTC"): FakePair(1.05), ("RAVE", "USD"): FakePair(1.0)}
PAIRS_DOWN = {("RAVE", "BTC"): FakePair(-4.0), ("RAVE", "USD"): FakePair(1.0)}
PAIRS_UNLISTED: dict = {}

#: ammo_cell arguments reaching all three AMMO_PATHS and all three TERRITORY_COLORS.
AMMO_CASES = {
    "scrum": {"holdings": 5.0, "cur_price": 20.0, "qrate": 1.0, "target_val": 50.0},
    "fold": {"holdings": 5.0, "cur_price": 5.0, "qrate": 1.0, "target_val": 50.0},
    "at_target": {"holdings": 5.0, "cur_price": 10.0, "qrate": 1.0, "target_val": 50.0},
    "manual_fire_noop": {
        "holdings": 5.0,
        "cur_price": 10.06,
        "qrate": 1.0,
        "target_val": 50.0,
    },
    "no_target": {"holdings": 5.0, "cur_price": 20.0, "qrate": 1.0, "target_val": 0.0},
    "empty": {"holdings": 0.0, "cur_price": 0.0, "qrate": 1.0, "target_val": 50.0},
    "pending": {"holdings": 5.0, "cur_price": 0.0, "qrate": 1.0, "target_val": 50.0},
    "stale": {
        "stats_pv": 100.0,
        "holdings": 0.0,
        "cur_price": 0.0,
        "qrate": 1.0,
        "target_val": 50.0,
    },
    "aged_price": {
        "holdings": 5.0,
        "cur_price": 20.0,
        "qrate": 1.0,
        "target_val": 50.0,
        "price_age_s": 25.0,
    },
    "crypto_quote": {
        "holdings": 5.0,
        "cur_price": 20.0,
        "qrate": 60000.0,
        "target_val": 50.0,
    },
    "tiny": {
        "holdings": 1e-06,
        "cur_price": 1e-06,
        "qrate": 1.0,
        "target_val": 1e-09,
    },
}

#: target_denom_cell arguments reaching all seven DENOM_PATHS and all three unit widths.
DENOM_CASES = {
    "priced_up": ({"pairs": PAIRS_UP}, ("BTC", "RAVE", "coinbase", 500.0)),
    "priced_down": ({"pairs": PAIRS_DOWN}, ("BTC", "RAVE", "coinbase", 500.0)),
    "priced_flat": ({"pairs": PAIRS_FLAT}, ("BTC", "RAVE", "coinbase", 500.0)),
    "priced_eth": ({"pairs": PAIRS_UP}, ("ETH", "RAVE", "coinbase", 500.0)),
    "units_whole": (
        {"pairs": PAIRS_UP, "btc_usd": 100.0},
        ("BTC", "RAVE", "coinbase", 500.0),
    ),
    "units_small": (
        {"pairs": PAIRS_UP, "btc_usd": 1000.0},
        ("BTC", "RAVE", "coinbase", 500.0),
    ),
    "units_tiny": (
        {"pairs": PAIRS_UP, "btc_usd": 60000.0},
        ("BTC", "RAVE", "coinbase", 0.5),
    ),
    "no_names": ({"pairs": PAIRS_UP}, ("", "RAVE", "coinbase", 500.0)),
    "self_reference": ({"pairs": PAIRS_UP}, ("BTC", "BTC", "coinbase", 500.0)),
    "no_target": ({"pairs": PAIRS_UP}, ("BTC", "RAVE", "coinbase", 0.0)),
    "no_rate": (
        {"pairs": PAIRS_UP, "btc_usd": 0.0},
        ("BTC", "RAVE", "coinbase", 500.0),
    ),
    "unlisted": ({"pairs": PAIRS_UNLISTED}, ("BTC", "RAVE", "coinbase", 500.0)),
    "errored": (
        {"pairs": PAIRS_UP, "scout_error": RuntimeError("the scout refused")},
        ("BTC", "RAVE", "coinbase", 500.0),
    ),
}


def ammo_payload(name: str) -> dict:
    return bridge_payload(ammo=dict(AMMO_CASES[name]))


def denom_case(name: str, monkeypatch) -> tuple:
    """One Target-denom payload, and the scout that answered it."""
    spec, args = DENOM_CASES[name]
    scout = install_market(monkeypatch, spec)
    quote, base, venue, target = args
    payload = bridge_payload(
        denom={
            "quote_currency": quote,
            "base_asset": base,
            "exchange_id": venue,
            "target_usd": target,
        }
    )
    return payload, scout


def denom_payload(name: str, monkeypatch) -> dict:
    return denom_case(name, monkeypatch)[0]


# -- the JavaScript engine ---------------------------------------------


class JsRuntime(JsEngine):
    """A QJSEngine holding ``table_cells.js`` and a ``window`` global."""

    module_path = MODULE_PATH
    setter = "acervatorSetCells"

    def load_tokens_and_themes(self) -> None:
        """Run unit 1's and unit 2's own modules, with the real payloads."""
        self.run(TOKENS_PATH.read_text(encoding="utf-8"))
        self.bind_json("TOKENS", token_payload())
        self.run("acervatorSetTokens(JSON.parse(TOKENS));")
        self.run(THEMES_PATH.read_text(encoding="utf-8"))
        self.bind_json("THEMES", theme_payload())
        self.run("acervatorSetThemes(JSON.parse(THEMES));")

    def call(self, expression: str, *args: Any) -> Any:
        self.bind_json("ARGS", list(args))
        return self.json(expression + ".apply(null, JSON.parse(ARGS))")


@pytest.fixture()
def js(qapp) -> JsRuntime:
    """The module, loaded in a fresh engine."""
    assert qapp is not None
    return JsRuntime(new_engine(), module_text())


@pytest.fixture()
def loaded(js: JsRuntime) -> JsRuntime:
    """The module holding one whole surface payload."""
    js.push(bridge_payload())
    return js


def test_the_module_names_every_field_the_surface_publishes(loaded: JsRuntime):
    surface = sorted(bridge_payload())
    module = sorted(loaded.json("acervatorCells.carriedNames()"))
    missing = sorted(set(surface) - set(module))
    extra = sorted(set(module) - set(surface))
    assert not missing, (
        f"{len(missing)} of {len(surface)} surface fields are never named "
        f"by the module: {missing}"
    )
    assert not extra, (
        f"{len(extra)} of {len(module)} module names have no surface " f"field: {extra}"
    )
    assert len(module) == len(surface) == len(set(surface))


def test_the_field_reach_check_names_a_field_only_the_surface_holds(js: JsRuntime):
    payload = bridge_payload()
    payload["planted_only_in_python"] = "planted"
    js.push(payload)
    module = set(js.json("acervatorCells.carriedNames()"))
    missing = set(payload) - module
    assert missing == {
        "planted_only_in_python"
    }, f"the check did not name the field only the surface holds: {missing}"


def test_the_field_reach_check_names_a_field_only_the_module_holds(js: JsRuntime):
    payload = bridge_payload()
    dropped = tcs.STALE_MARKER and "stale_marker"
    del payload[dropped]
    js.push(payload)
    module = set(js.json("acervatorCells.carriedNames()"))
    extra = module - set(payload)
    assert extra == {
        dropped
    }, f"the check did not name the field only the module holds: {extra}"


def test_every_named_field_answers_with_the_surface_value(loaded: JsRuntime):
    payload = bridge_payload()
    names = loaded.json("acervatorCells.carriedNames()")
    differing = {}
    for name in names:
        held = loaded.call("acervatorCells.field", name)
        if held != payload[name]:
            differing[name] = (payload[name], held)
    assert not differing, (
        f"{len(differing)} of {len(names)} fields differ between the "
        f"surface and the module: {differing}"
    )


def test_the_value_check_names_a_field_whose_value_was_changed(js: JsRuntime):
    payload = bridge_payload()
    payload["column_count"] = payload["column_count"] + 1
    js.push(payload)
    held = js.call("acervatorCells.field", "column_count")
    assert held == payload["column_count"]
    assert held != tcs.COLUMN_COUNT


def test_the_whole_payload_reads_back_unchanged(loaded: JsRuntime):
    assert loaded.json("acervatorCells.payload()") == bridge_payload()


def test_the_declared_and_held_field_counts_are_reported_apart(loaded: JsRuntime):
    counts = loaded.push(bridge_payload())
    assert counts["declared"]["fields"] == len(bridge_payload())
    assert counts["held"]["fields"] == counts["declared"]["fields"]


def test_a_short_payload_reads_as_fewer_held_than_declared(js: JsRuntime):
    payload = bridge_payload()
    del payload["skin"]
    del payload["style_sheet"]
    counts = js.push(payload)
    assert counts["declared"]["fields"] == len(bridge_payload())
    assert counts["held"]["fields"] == counts["declared"]["fields"] - 2


#: tcs names table_cells.js may write: METHOD and the AMMO_CELL payload key.
NAME_EXCEPTIONS = {tcs.METHOD, tcs.AMMO_CELL}


def surface_values() -> set:
    """Returns every tcs constant and table value as text, less NAME_EXCEPTIONS."""
    found = {
        str(value)
        for name, value in vars(tcs).items()
        if name.isupper() and isinstance(value, (str, int, float))
        if not isinstance(value, bool)
    }
    for table in (tcs.TERRITORY_COLORS, tcs.TERRITORY_TIPS, tcs.DENOM_PATH_TEXTS):
        found.update(str(value) for value in table.values())
    for table in (tcs.CELL_COLUMNS, tcs.CELL_MASK_KEYS, tcs.CELL_QUOTES):
        found.update(str(value) for value in table.values())
    found.discard("")
    return found - NAME_EXCEPTIONS


def drawn_values() -> set:
    """Returns the tcs colours, texts, formats and numbers a Cell draws."""
    found = set(tcs.TERRITORY_COLORS.values())
    found.update(tcs.TERRITORY_TIPS.values())
    found.update(tcs.DENOM_PATH_TEXTS.values())
    found.update(str(value) for value in tcs.CELL_QUOTES.values())
    found.update(str(value) for value in tcs.CELL_COLUMNS.values())
    found.update(
        [
            tcs.STALE_MARKER,
            tcs.NO_TARGET_TEXT,
            tcs.PENDING_PRICE_TEXT,
            tcs.PENDING_RATE_TEXT,
            tcs.UNLISTED_TEXT,
            tcs.ALIGNMENT,
            tcs.SIGN_UP,
            tcs.MAGNITUDE_FORMAT,
            tcs.STALE_TEXT_FORMAT,
            tcs.DENOM_TEXT_FORMAT,
            tcs.UNITS_WHOLE_FORMAT,
            tcs.UNITS_SMALL_FORMAT,
            tcs.UNITS_TINY_FORMAT,
            str(tcs.ALIGNMENT_VALUE),
            str(tcs.COLUMN_COUNT),
            str(tcs.PRICE_STALE_AFTER_S),
            str(tcs.MANUAL_FIRE_DUST_PCT),
            str(tcs.DIVERGENCE_DUST_PCT),
        ]
    )
    found.discard("")
    return found


def literal_findings(source: str) -> dict:
    """Every kind of written-in value the module must not carry."""
    found = js_literals(source)
    return {
        "numbers": found["numbers"],
        "slashes": found["slashes"],
        "colours": HEX_COLOUR.findall(source),
        "surface_values": sorted(set(found["strings"]) & surface_values()),
    }


@pytest.fixture(scope="module")
def module_source() -> str:
    return module_text()


def test_the_module_writes_no_number(module_source: str):
    found = literal_findings(module_source)["numbers"]
    assert not found, f"table_cells.js holds numeric literals: {found}"


def test_the_module_writes_no_colour(module_source: str):
    found = literal_findings(module_source)["colours"]
    assert not found, f"table_cells.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_surface_value(module_source: str):
    found = literal_findings(module_source)["surface_values"]
    assert not found, f"table_cells.js spells out surface values: {found}"


def test_no_string_in_the_module_equals_a_design_token_value(module_source: str):
    values = {str(value) for value in dss.TOKENS.values()}
    written = sorted(set(js_literals(module_source)["strings"]) & values)
    assert not written, f"table_cells.js spells out token values: {written}"


def test_the_module_hides_no_value_behind_a_regular_expression(module_source: str):
    found = literal_findings(module_source)["slashes"]
    assert not found, (
        "table_cells.js holds a slash outside a comment, which the "
        f"literal scan cannot read: {found}"
    )


#: One line per kind, appended to MODULE_PATH and then removed again.
APPENDED_LINES = {
    "colour": 'var planted = "' + tcs.AMMO_SCRUM_COLOR + '";',
    "number": "var planted = " + str(tcs.ALIGNMENT_VALUE) + ";",
    "threshold": "var planted = " + str(tcs.PRICE_STALE_AFTER_S) + ";",
    "format": 'var planted = "' + tcs.MAGNITUDE_FORMAT + '";',
    "marker": 'var planted = "' + tcs.STALE_MARKER + '";',
    "tip": 'var planted = "' + tcs.SCRUM_TIP + '";',
    "mask_key": 'var planted = "' + tcs.CELL_MASK_KEYS[AMMO_CELL] + '";',
    "regex": "var planted = /ab+c/;",
}

APPENDED_KINDS = {
    "colour": ("colours", "surface_values"),
    "number": ("numbers",),
    "threshold": ("numbers",),
    "format": ("surface_values",),
    "marker": ("surface_values",),
    "tip": ("surface_values",),
    "mask_key": ("surface_values",),
    "regex": ("slashes",),
}


def digest_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("kind", sorted(APPENDED_LINES))
def test_the_literal_scan_names_a_value_appended_to_the_module_file(kind: str):
    with module_file_held():
        before = MODULE_PATH.read_bytes()
        before_digest = hashlib.sha256(before).hexdigest()
        appended = before + ("\n" + APPENDED_LINES[kind] + "\n").encode("utf-8")
        try:
            swap_module(MODULE_PATH, appended)
            assert digest_of(MODULE_PATH) != before_digest
            found = literal_findings(MODULE_PATH.read_text(encoding="utf-8"))
            named = {name for name in APPENDED_KINDS[kind] if found[name]}
            reported = {name: found[name] for name in APPENDED_KINDS[kind]}
            assert named == set(
                APPENDED_KINDS[kind]
            ), f"literal_findings did not name the added {kind}: {reported}"
        finally:
            swap_module(MODULE_PATH, before)
        assert MODULE_PATH.read_bytes() == before, f"{MODULE_PATH} was not restored"
        assert digest_of(MODULE_PATH) == before_digest, (
            f"{MODULE_PATH} changed: " f"{before_digest} -> {digest_of(MODULE_PATH)}"
        )


def test_module_file_held_refuses_a_second_mkdir_while_lock_path_exists():
    for _ in range(2):
        with module_file_held():
            assert LOCK_PATH.exists()
            with pytest.raises(FileExistsError):
                LOCK_PATH.mkdir()


def test_every_scan_exception_is_a_name_and_not_a_value(loaded: JsRuntime):
    payload = bridge_payload()
    drawn = drawn_values()
    for name in NAME_EXCEPTIONS:
        assert name not in drawn, f"{name} is a value the surface draws"
    assert tcs.AMMO_CELL in payload, "the Ammo cell name is not a payload field"
    assert tcs.AMMO_CELL in payload["cells"]
    assert loaded.json("acervatorCells.method") == tcs.METHOD
    assert len(NAME_EXCEPTIONS) == 2, sorted(NAME_EXCEPTIONS)


def test_the_narrow_and_broad_value_lists_agree_on_every_drawn_value():
    unseen = drawn_values() - surface_values() - NAME_EXCEPTIONS
    assert not unseen, f"the sweep does not see these drawn values: {unseen}"


def test_the_shipped_module_file_holds_no_literal(module_source: str):
    found = literal_findings(module_source)
    assert not any(found.values()), f"the clean module reported: {found}"


@pytest.mark.parametrize("name", sorted(AMMO_CASES))
def test_the_ammo_cell_reaches_the_module_value_for_value(name: str, js: JsRuntime):
    payload = ammo_payload(name)
    js.push(payload)
    assert js.json("acervatorCells.ammo()") == payload["ammo"]
    assert js.json("acervatorCells.ammoPath()") == payload["ammo_path"]
    assert payload["ammo_path"] in tcs.AMMO_PATHS


@pytest.mark.parametrize("name", sorted(AMMO_CASES))
def test_every_ammo_value_keeps_its_type_across_the_bridge(name: str, js: JsRuntime):
    payload = ammo_payload(name)
    js.push(payload)
    expected = {
        field: JS_TYPE_OF[type(value).__name__]
        for field, value in payload["ammo"].items()
    }
    assert js.call("acervatorCells.types", "ammo") == expected


@pytest.mark.parametrize("name", sorted(DENOM_CASES))
def test_the_denom_cell_reaches_the_module_value_for_value(
    name: str, js: JsRuntime, monkeypatch
):
    payload = denom_payload(name, monkeypatch)
    js.push(payload)
    assert js.json("acervatorCells.denom()") == payload["denom"]
    assert js.json("acervatorCells.denomPath()") == payload["denom_path"]
    assert payload["denom_path"] in tcs.DENOM_PATHS


@pytest.mark.parametrize("name", sorted(DENOM_CASES))
def test_every_denom_value_keeps_its_type_across_the_bridge(
    name: str, js: JsRuntime, monkeypatch
):
    payload = denom_payload(name, monkeypatch)
    js.push(payload)
    expected = {
        field: JS_TYPE_OF[type(value).__name__]
        for field, value in payload["denom"].items()
    }
    assert js.call("acervatorCells.types", "denom") == expected


def test_the_priced_case_asks_the_scout_for_the_venue_it_was_given(monkeypatch):
    payload, scout = denom_case("priced_up", monkeypatch)
    assert payload["denom_path"] == tcs.DENOM_PATH_PRICED
    venues = {venue for _, _, venue in scout.asked}
    assert venues == {"coinbase"}, f"the scout was asked for {venues}"
    assert ("RAVE", "BTC", "coinbase") in scout.asked
    assert ("RAVE", "USD", "coinbase") in scout.asked


def test_the_cases_cover_every_path_the_surface_publishes(monkeypatch):
    ammo_paths = {ammo_payload(name)["ammo_path"] for name in AMMO_CASES}
    denom_paths = {denom_payload(n, monkeypatch)["denom_path"] for n in DENOM_CASES}
    assert ammo_paths == set(tcs.AMMO_PATHS), f"Ammo paths not covered: {ammo_paths}"
    assert denom_paths == set(
        tcs.DENOM_PATHS
    ), f"denom paths not covered: {denom_paths}"


def test_the_cases_cover_every_colour_the_surface_publishes(monkeypatch):
    drawn = {ammo_payload(name)["ammo"]["color"] for name in AMMO_CASES}
    drawn.update(
        denom_payload(name, monkeypatch)["denom"]["color"] for name in DENOM_CASES
    )
    assert set(tcs.TERRITORY_COLORS.values()) <= drawn, (
        "the case table never draws " f"{set(tcs.TERRITORY_COLORS.values()) - drawn}"
    )


def test_the_cases_cover_all_three_unit_widths(monkeypatch):
    texts = {
        denom_payload(name, monkeypatch)["denom"]["text"]
        for name in ("units_whole", "units_small", "units_tiny")
    }
    widths = {len(text.split(" ")[0].split(".")[-1]) for text in texts}
    assert widths == {4, 5, 6}, f"the three unit widths were not all drawn: {texts}"


def test_the_agreement_check_names_a_changed_cell_value(js: JsRuntime):
    payload = ammo_payload("scrum")
    payload["ammo"]["text"] = payload["ammo"]["text"] + "0"
    js.push(payload)
    held = js.json("acervatorCells.ammo()")
    assert held == payload["ammo"]
    assert held["text"] != ammo_payload("scrum")["ammo"]["text"]


def test_the_type_check_names_a_colour_that_arrived_as_a_number(js: JsRuntime):
    payload = ammo_payload("scrum")
    payload["ammo"]["color"] = 255
    js.push(payload)
    assert js.call("acervatorCells.types", "ammo")["color"] == "number"


@pytest.mark.parametrize("name", sorted(AMMO_CASES))
def test_the_module_reports_no_fault_on_a_real_ammo_payload(name: str, js: JsRuntime):
    counts = js.push(ammo_payload(name))
    assert counts["faults"] == [], f"{name}: {counts['faults']}"


@pytest.mark.parametrize("name", sorted(DENOM_CASES))
def test_the_module_reports_no_fault_on_a_real_denom_payload(
    name: str, js: JsRuntime, monkeypatch
):
    counts = js.push(denom_payload(name, monkeypatch))
    assert counts["faults"] == [], f"{name}: {counts['faults']}"


def test_the_module_reads_the_per_cell_tables_the_surface_publishes(loaded: JsRuntime):
    for name in tcs.CELLS:
        assert loaded.call("acervatorCells.column", name) == tcs.CELL_COLUMNS[name]
        assert loaded.call("acervatorCells.maskKey", name) == tcs.CELL_MASK_KEYS[name]
        assert loaded.call("acervatorCells.wantsTooltip", name) == (
            tcs.CELL_TOOLTIPS[name]
        )
        assert loaded.call("acervatorCells.wantsIcon", name) == tcs.CELL_ICONS[name]
        assert loaded.call("acervatorCells.quote", name) == tcs.CELL_QUOTES.get(name)


def test_the_module_reads_every_territory_colour_and_tip(loaded: JsRuntime):
    for name in tcs.TERRITORIES:
        assert loaded.call("acervatorCells.territoryColour", name) == (
            tcs.TERRITORY_COLORS[name]
        )
        assert loaded.call("acervatorCells.territoryTip", name) == (
            tcs.TERRITORY_TIPS[name]
        )


def test_the_engine_call_trace_reaches_the_module_unchanged(js: JsRuntime):
    payload = ammo_payload("scrum")
    js.push(payload)
    assert js.json("acervatorCells.calls()") == payload["calls"]
    assert payload["calls"], "the case drove no engine call at all"


def token_carriers(printed: str) -> list:
    """Every non-alias design token carrying ``printed``."""
    payload = token_payload()
    aliases = payload.get("alias_targets", {})
    return sorted(
        name
        for name, value in payload["tokens"].items()
        if name not in aliases and str(value) == printed
    )


def test_a_colour_one_token_carries_is_painted_through_that_token(js: JsRuntime):
    js.load_tokens_and_themes()
    colour = tcs.TERRITORY_COLORS[tcs.TERRITORY_SCRUM]
    assert len(token_carriers(colour)) == 1
    name = token_carriers(colour)[0]
    assert js.call("acervatorCells.variableFor", colour) == name
    assert js.call("acervatorCells.colour", colour) == (
        "var(--" + name + ", " + colour + ")"
    )


def test_a_colour_two_names_carry_is_painted_from_the_surface(js: JsRuntime):
    js.load_tokens_and_themes()
    colour = tcs.TERRITORY_COLORS[tcs.TERRITORY_AT_TARGET]
    payload = token_payload()
    all_carriers = sorted(
        name for name, value in payload["tokens"].items() if str(value) == colour
    )
    assert len(all_carriers) > 1, f"{colour} is no longer carried by two names"
    assert len(token_carriers(colour)) == 1, "the alias exclusion no longer applies"
    js.bind_json(
        "TWO", {"token_names": ["A", "B"], "tokens": {"A": colour, "B": colour}}
    )
    js.run("acervatorSetTokens(JSON.parse(TWO));")
    assert js.call("acervatorCells.variableFor", colour) is None
    assert js.call("acervatorCells.colour", colour) == colour


def test_a_colour_no_name_carries_is_painted_from_the_surface(js: JsRuntime):
    js.load_tokens_and_themes()
    unheld = tcs.TERRITORY_COLORS[tcs.TERRITORY_SCRUM] + "01"
    assert js.call("acervatorCells.variableFor", unheld) is None
    assert js.call("acervatorCells.colour", unheld) == unheld


def test_the_resolver_answers_nothing_without_the_token_module(js: JsRuntime):
    colour = tcs.TERRITORY_COLORS[tcs.TERRITORY_SCRUM]
    assert js.call("acervatorCells.variableFor", colour) is None
    assert js.call("acervatorCells.colour", colour) == colour


def test_the_cell_style_paints_the_colour_the_surface_gave_it(js: JsRuntime):
    js.load_tokens_and_themes()
    payload = ammo_payload("scrum")
    js.push(payload)
    style = js.call("acervatorCells.cellStyle", payload["ammo"])
    assert style == {
        "color": js.call("acervatorCells.colour", payload["ammo"]["color"])
    }


INHERITED_NAMES = ("constructor", "toString", "hasOwnProperty", "__proto__", "valueOf")


@pytest.mark.parametrize("name", INHERITED_NAMES)
def test_a_lookup_never_answers_with_an_inherited_method(name: str, loaded: JsRuntime):
    for reader in ("field", "column", "quote", "maskKey", "wantsTooltip", "wantsIcon"):
        assert loaded.call("acervatorCells." + reader, name) is None, (
            reader + " " + name
        )
    assert loaded.call("acervatorCells.territoryColour", name) is None
    assert loaded.call("acervatorCells.territoryTip", name) is None


def test_a_lookup_answers_for_a_name_the_payload_does_carry(
    loaded: JsRuntime,
):
    assert (
        loaded.call("acervatorCells.column", AMMO_CELL) == tcs.CELL_COLUMNS[AMMO_CELL]
    )
    assert loaded.call("acervatorCells.field", "column_count") == tcs.COLUMN_COUNT


def test_the_module_reports_a_missing_bridge_rather_than_raising(js: JsRuntime):
    js.run("acervatorLoadCells();")
    drain_events()
    assert js.json("acervatorCells.isLoaded()") is False
    assert js.json("acervatorCells.loadError()") == "the preload bridge is not present"


def test_a_refused_ask_is_not_remembered(js: JsRuntime):
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(
        "window.TRIES = 0;"
        "window.acervator = { call: function () {"
        "  window.TRIES += 1;"
        "  if (window.TRIES === 1) {"
        "    return Promise.reject(new Error('the Python backend is not running')); }"
        "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
        "acervatorLoadCells();"
    )
    drain_events()
    assert js.json("acervatorCells.isLoaded()") is False
    assert js.json("acervatorCells.loadError()") == "the Python backend is not running"
    js.run("acervatorLoadCells();")
    drain_events()
    assert js.json("window.TRIES") == 2
    assert js.json("acervatorCells.isLoaded()") is True
    assert js.json("acervatorCells.cellNames()") == list(tcs.CELLS)


def test_one_page_asks_the_backend_once(js: JsRuntime):
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(
        "window.TRIES = 0;"
        "window.acervator = { call: function () {"
        "  window.TRIES += 1;"
        "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
        "acervatorLoadCells();acervatorLoadCells();acervatorLoadCells();"
    )
    drain_events()
    assert js.json("window.TRIES") == 1
    assert js.json("acervatorCells.isLoaded()") is True


def hostile_payloads() -> dict:
    """One payload per hostile shape, each built from a real one."""
    found = {}

    missing_rule = bridge_payload()
    del missing_rule["territory_colors"]
    found["rule_missing"] = missing_rule

    null_rule = bridge_payload()
    null_rule["territory_colors"] = None
    found["rule_null"] = null_rule

    missing_cell_rule = bridge_payload()
    del missing_cell_rule["cell_columns"][AMMO_CELL]
    found["cell_rule_missing"] = missing_cell_rule

    colour_number = ammo_payload("scrum")
    colour_number["ammo"]["color"] = 16711808
    found["colour_is_a_number"] = colour_number

    threshold_text = bridge_payload()
    threshold_text["price_stale_after_s"] = "twenty seconds"
    threshold_text["manual_fire_dust_pct"] = "one percent"
    found["threshold_is_text"] = threshold_text

    format_shape = bridge_payload()
    format_shape["stale_marker"] = ["s", "t", "a", "l", "e"]
    format_shape["denom_path_texts"] = "not a table"
    found["format_wrong_shape"] = format_shape

    ammo_null = ammo_payload("scrum")
    ammo_null["ammo"] = None
    found["ammo_is_null"] = ammo_null

    ammo_list = ammo_payload("scrum")
    ammo_list["ammo"] = ["text", "color"]
    found["ammo_is_a_list"] = ammo_list

    ammo_gone = ammo_payload("scrum")
    del ammo_gone["ammo"]
    found["ammo_is_absent"] = ammo_gone

    short_ammo = ammo_payload("scrum")
    del short_ammo["ammo"]["tip"]
    found["ammo_field_missing"] = short_ammo

    long_ammo = ammo_payload("scrum")
    long_ammo["ammo"]["planted"] = "planted"
    found["ammo_field_unexpected"] = long_ammo

    unknown_path = ammo_payload("scrum")
    unknown_path["ammo_path"] = "planted_path"
    found["ammo_path_unknown"] = unknown_path

    return found


#: The fault kinds acervatorCells.faults must hold for each hostile_payloads entry.
HOSTILE_FAULTS = {
    "rule_missing": set(),
    "rule_null": set(),
    "cell_rule_missing": {"missing"},
    "colour_is_a_number": set(),
    "threshold_is_text": set(),
    "format_wrong_shape": set(),
    "ammo_is_null": {"null"},
    "ammo_is_a_list": {"not-a-table"},
    "ammo_is_absent": {"missing"},
    "ammo_field_missing": {"unknown-field-set", "missing"},
    "ammo_field_unexpected": {"unknown-field-set", "unexpected"},
    "ammo_path_unknown": {"unknown-path"},
}


@pytest.mark.parametrize("name", sorted(HOSTILE_FAULTS))
def test_a_hostile_payload_is_reported_and_not_repaired(name: str, js: JsRuntime):
    payload = hostile_payloads()[name]
    counts = js.push(payload)
    raised = {entry["fault"] for entry in counts["faults"]}
    assert raised == HOSTILE_FAULTS[name], (
        f"{name} raised {sorted(raised)}, expected "
        f"{sorted(HOSTILE_FAULTS[name])}: {counts['faults']}"
    )


@pytest.mark.parametrize("name", sorted(HOSTILE_FAULTS))
def test_a_hostile_payload_still_answers_every_acervator_cells_function(
    name: str, js: JsRuntime
):
    js.push(hostile_payloads()[name])
    assert js.json("acervatorCells.isLoaded()") is True
    assert isinstance(js.json("acervatorCells.payload()"), dict)
    assert isinstance(js.json("acervatorCells.cellNames()"), list)
    assert isinstance(js.json("acervatorCells.ammo()"), dict)
    assert isinstance(js.json("acervatorCells.denom()"), dict)
    assert isinstance(js.call("acervatorCells.types", "ammo"), dict)


def test_a_payload_that_is_not_a_table_is_reported_apart(js: JsRuntime):
    refusals: tuple[Any, ...] = ([], "text", 12, None, True)
    for hostile in refusals:
        js.bind_json("PAYLOAD", hostile)
        counts = js.json("acervatorSetCells(JSON.parse(PAYLOAD))")
        assert counts["declared"] is None and counts["held"] is None
        assert [entry["fault"] for entry in counts["faults"]] == ["not-an-object"]
        assert js.json("acervatorCells.isLoaded()") is False


HOSTILE_CELL_VALUES = {
    "null": None,
    "number": 12,
    "list": ["a", "b"],
    "table": {"a": "b"},
    "flag": True,
    "empty_text": "",
}


@pytest.mark.parametrize("kind", sorted(HOSTILE_CELL_VALUES))
def test_a_hostile_cell_value_reaches_the_module_as_it_arrived(
    kind: str, js: JsRuntime
):
    payload = ammo_payload("scrum")
    payload["ammo"]["text"] = HOSTILE_CELL_VALUES[kind]
    js.push(payload)
    assert js.json("acervatorCells.ammo()")["text"] == HOSTILE_CELL_VALUES[kind]
    assert (
        js.call("acervatorCells.types", "ammo")["text"]
        == JS_TYPE_OF[type(HOSTILE_CELL_VALUES[kind]).__name__]
    )


def test_a_short_cell_table_reads_as_fewer_held_than_declared(js: JsRuntime):
    payload = bridge_payload()
    del payload["cell_columns"][ETH_CELL]
    counts = js.push(payload)
    assert counts["declared"]["cells"] == len(tcs.CELLS)
    assert counts["held"]["cells"] == len(tcs.CELLS) - 1


def test_the_denom_text_is_held_against_the_text_its_path_declares(js: JsRuntime):
    payload = bridge_payload(
        denom={
            "quote_currency": "BTC",
            "base_asset": "BTC",
            "exchange_id": "coinbase",
            "target_usd": 500.0,
        }
    )
    assert payload["denom_path"] == tcs.DENOM_PATH_SELF
    payload["denom"]["text"] = "planted"
    counts = js.push(payload)
    raised = [entry for entry in counts["faults"] if entry["fault"] == "text-mismatch"]
    assert len(raised) == 1, counts["faults"]
    assert raised[0]["detail"] == {
        "declared": tcs.DENOM_PATH_TEXTS[tcs.DENOM_PATH_SELF],
        "held": "planted",
    }


def test_the_priced_denom_path_declares_no_fixed_text(js: JsRuntime, monkeypatch):
    payload = denom_payload("priced_up", monkeypatch)
    assert payload["denom_path"] == tcs.DENOM_PATH_PRICED
    assert tcs.DENOM_PATH_PRICED not in payload["denom_path_texts"]
    counts = js.push(payload)
    assert counts["faults"] == []


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
        """Opens the page again while the module global stays absent."""
        for attempt in range(PAGE_ATTEMPTS):
            if attempt:
                self.open_page()
            for _ in range(READY_ROUNDS):
                if self.js("typeof window.acervatorCells") == "object":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined acervatorCells: readyState "
            + str(self.js("document.readyState"))
            + ", scripts "
            + str(self.js("document.scripts.length"))
            + ", tokens "
            + str(self.js("typeof window.acervatorTokens"))
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

    def value(self, expression: str) -> Any:
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
    with module_file_held():
        page = Browser()
    yield page
    page.close()


#: Applies the tokens, calls renderCell per cell, and adds one span per colour.
DRAW = (
    "(function (payload, colours) {"
    "  acervatorTokens.forget();"
    "  acervatorSetTokens(JSON.parse(window.TOKENS));"
    "  acervatorTokens.apply(document.documentElement);"
    "  acervatorSetCells(payload);"
    "  var host = document.getElementById('cells');"
    "  if (host === null) {"
    "    host = document.createElement('div');"
    "    host.id = 'cells';"
    "    document.body.appendChild(host); }"
    "  acervatorCells.cellNames().forEach(function (name) {"
    "    var at = document.getElementById('at-' + name);"
    "    if (at === null) {"
    "      at = document.createElement('div');"
    "      at.id = 'at-' + name;"
    "      host.appendChild(at); }"
    "    acervatorCells.renderCell(at, name); });"
    "  var probes = document.getElementById('probes');"
    "  if (probes === null) {"
    "    probes = document.createElement('div');"
    "    probes.id = 'probes';"
    "    document.body.appendChild(probes); }"
    "  probes.textContent = '';"
    "  colours.forEach(function (value, at) {"
    "    var probe = document.createElement('span');"
    "    probe.id = 'probe-' + at;"
    "    probe.style.color = value;"
    "    probes.appendChild(probe); });"
    "  return true; })"
)

READ = (
    "(function (name) {"
    "  var at = document.getElementById('at-' + name);"
    "  var cell = at.firstElementChild;"
    "  if (cell === null) { return null; }"
    "  var found = { tag: cell.tagName.toLowerCase(),"
    "    text: cell.textContent,"
    "    colour: getComputedStyle(cell).color,"
    "    inline: cell.style.color,"
    "    title: cell.hasAttribute('title') ? cell.getAttribute('title') : null };"
    "  ['data-cell','data-column','data-quote','data-mask-key','data-alignment',"
    "   'data-alignment-value','data-icon','data-path','data-stale',"
    "   'aria-label'].forEach(function (key) {"
    "    found[key] = cell.hasAttribute(key) ? cell.getAttribute(key) : null; });"
    "  return found; })"
)

PROBE_COLOUR = (
    "(function (at) {"
    "  return getComputedStyle("
    "    document.getElementById('probe-' + at)).color; })"
)


def draw_cells(browser: Browser, payload: dict, colours: list) -> None:
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js("window.COLOURS = " + json.dumps(json.dumps(colours)) + ";")
    assert (
        browser.value(DRAW + "(JSON.parse(window.PAYLOAD), JSON.parse(window.COLOURS))")
        is True
    )


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorCells") == "object"
    assert browser.js("typeof window.acervatorSetCells") == "function"
    assert browser.js("typeof window.acervatorLoadCells") == "function"


def test_the_module_makes_no_network_call_of_its_own(browser: Browser):
    browser.js(
        "window.VIOLATIONS = [];"
        "document.addEventListener('securitypolicyviolation', function (e) {"
        "  window.VIOLATIONS.push(e.violatedDirective + ' ' + e.blockedURI); });"
    )
    draw_cells(browser, ammo_payload("scrum"), [])
    browser.settle(500)
    assert browser.value("window.VIOLATIONS") == []


def test_the_drawn_cell_matches_what_the_surface_describes(browser: Browser):
    payload = ammo_payload("scrum")
    draw_cells(browser, payload, [payload["ammo"]["color"]])
    drawn = browser.value(READ + "(" + json.dumps(AMMO_CELL) + ")")
    assert drawn["tag"] == "td"
    assert drawn["text"] == payload["ammo"]["text"]
    assert drawn["title"] == payload["ammo"]["tip"]
    assert drawn["data-cell"] == AMMO_CELL
    assert drawn["data-column"] == str(payload["cell_columns"][AMMO_CELL])
    assert drawn["data-mask-key"] == payload["cell_mask_keys"][AMMO_CELL]
    assert drawn["data-alignment"] == payload["alignment"]
    assert drawn["data-alignment-value"] == str(payload["alignment_value"])
    assert drawn["data-icon"] == str(payload["cell_icons"][AMMO_CELL]).lower()
    assert drawn["data-path"] == payload["ammo_path"]
    assert drawn["data-stale"] == str(payload["ammo"]["stale"]).lower()
    assert drawn["data-quote"] is None
    probe = browser.value(PROBE_COLOUR + "(0)")
    assert drawn["colour"] == probe, (
        "the drawn colour differs from a probe styled straight from the "
        f"surface value {payload['ammo']['color']}: {drawn['colour']} vs {probe}"
    )


def test_a_denom_cell_draws_its_quote_and_no_tooltip(browser: Browser, monkeypatch):
    payload = denom_payload("priced_up", monkeypatch)
    draw_cells(browser, payload, [payload["denom"]["color"]])
    for name in (BTC_CELL, ETH_CELL):
        drawn = browser.value(READ + "(" + json.dumps(name) + ")")
        assert drawn["text"] == payload["denom"]["text"]
        assert drawn["data-quote"] == payload["cell_quotes"][name]
        assert drawn["data-path"] == payload["denom_path"]
        assert drawn["title"] is None, "a denom cell drew a tooltip"
        assert drawn["data-column"] == str(payload["cell_columns"][name])


def test_the_drawn_check_names_a_changed_cell_text(browser: Browser):
    payload = ammo_payload("scrum")
    payload["ammo"]["text"] = payload["ammo"]["text"] + "0"
    draw_cells(browser, payload, [])
    drawn = browser.value(READ + "(" + json.dumps(AMMO_CELL) + ")")
    assert drawn["text"] == payload["ammo"]["text"]
    assert drawn["text"] != ammo_payload("scrum")["ammo"]["text"]


@pytest.mark.parametrize("name", ("scrum", "fold", "at_target", "stale", "pending"))
def test_every_ammo_path_draws_the_colour_the_surface_gave_it(
    name: str, browser: Browser
):
    payload = ammo_payload(name)
    draw_cells(browser, payload, [payload["ammo"]["color"]])
    drawn = browser.value(READ + "(" + json.dumps(AMMO_CELL) + ")")
    assert drawn["colour"] == browser.value(PROBE_COLOUR + "(0)")
    assert drawn["text"] == payload["ammo"]["text"]


def test_rewriting_a_token_moves_the_cell_and_nothing_else(browser: Browser):
    payload = ammo_payload("scrum")
    colour = payload["ammo"]["color"]
    carriers = token_carriers(colour)
    assert len(carriers) == 1, f"{colour} is carried by {carriers}"
    token = carriers[0]
    other = tcs.TERRITORY_COLORS[tcs.TERRITORY_FOLD]
    draw_cells(browser, payload, [colour, other])

    before = {n: browser.value(READ + "(" + json.dumps(n) + ")") for n in tcs.CELLS}
    assert before[AMMO_CELL]["inline"].startswith("var(--" + token), (
        "the cell did not paint through a token at all: "
        f"{before[AMMO_CELL]['inline']}"
    )
    browser.js(
        "document.documentElement.style.setProperty('--"
        + token
        + "', "
        + json.dumps(other)
        + ");"
    )
    after = {n: browser.value(READ + "(" + json.dumps(n) + ")") for n in tcs.CELLS}

    assert after[AMMO_CELL]["colour"] == browser.value(PROBE_COLOUR + "(1)"), (
        "the cell did not follow the rewritten token: "
        f"{after[AMMO_CELL]['colour']} vs the probe for {other}"
    )
    assert after[AMMO_CELL]["colour"] != before[AMMO_CELL]["colour"]
    moved = [n for n in tcs.CELLS if after[n]["colour"] != before[n]["colour"]]
    assert moved == [AMMO_CELL], f"the token rewrite moved other cells too: {moved}"
    unchanged = [n for n in tcs.CELLS if after[n] == before[n]]
    assert set(unchanged) == set(tcs.CELLS) - {AMMO_CELL}
    assert browser.value(PROBE_COLOUR + "(0)") == before[AMMO_CELL]["colour"], (
        "the probe moved with the token, so it is not an independent "
        "reading of the surface value"
    )


def test_a_cell_drawn_with_no_tokens_ignores_a_rewritten_token(
    browser: Browser,
):
    payload = ammo_payload("scrum")
    colour = payload["ammo"]["color"]
    token = token_carriers(colour)[0]
    other = tcs.TERRITORY_COLORS[tcs.TERRITORY_FOLD]
    browser.js("window.TOKENS = " + json.dumps(json.dumps({"tokens": {}})) + ";")
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js("window.COLOURS = " + json.dumps(json.dumps([colour])) + ";")
    browser.value(DRAW + "(JSON.parse(window.PAYLOAD), JSON.parse(window.COLOURS))")
    before = browser.value(READ + "(" + json.dumps(AMMO_CELL) + ")")
    assert not before["inline"].startswith("var(--"), (
        "with no token table the cell must paint the plain colour, not a "
        f"variable: {before['inline']}"
    )
    assert before["colour"] == browser.value(PROBE_COLOUR + "(0)")
    browser.js(
        "document.documentElement.style.setProperty('--"
        + token
        + "', "
        + json.dumps(other)
        + ");"
    )
    after = browser.value(READ + "(" + json.dumps(AMMO_CELL) + ")")
    assert after["colour"] == before["colour"], (
        "a cell painted from a plain colour followed a token rewrite, so "
        "the control above cannot tell the two apart"
    )


def test_a_hostile_cell_value_still_draws_a_cell(browser: Browser):
    payload = ammo_payload("scrum")
    payload["ammo"]["color"] = 16711808
    payload["ammo"]["text"] = None
    payload["ammo"]["tip"] = ""
    draw_cells(browser, payload, [])
    drawn = browser.value(READ + "(" + json.dumps(AMMO_CELL) + ")")
    assert drawn["tag"] == "td"
    assert drawn["text"] == ""
    assert drawn["title"] is None
    assert drawn["inline"] == ""


def test_the_module_parses_as_plain_javascript(qapp):
    qtqml = pytest.importorskip("PySide6.QtQml")
    assert qapp is not None
    engine = qtqml.QJSEngine()
    engine.evaluate("var window = this;")
    result = engine.evaluate(module_text(), MODULE_PATH.name)
    assert not result.isError(), result.toString()
    broken = engine.evaluate("(function(){ var = ; })", "control")
    assert broken.isError(), "the parser accepted broken JavaScript"


def test_the_page_loads_the_module_after_the_theme_engine():
    html = INDEX_HTML.read_text(encoding="utf-8")
    order = re.findall(r'<script src="([^"]+)"', html)
    names = [Path(ref).name for ref in order]
    assert "table_cells.js" in names, names
    assert names.index("table_cells.js") > names.index("theme_engine.js")
    assert names.index("table_cells.js") > names.index("design_tokens.js")
    assert names.index("table_cells.js") > names.index("react.production.min.js")


def test_the_page_names_the_module_at_a_path_that_exists():
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = [
        r for r in re.findall(r'src="([^"]+)"', html) if r.endswith("table_cells.js")
    ]
    assert len(refs) == 1, refs
    resolved = (INDEX_HTML.parent / refs[0]).resolve()
    assert resolved.is_file()
    assert resolved == MODULE_PATH
