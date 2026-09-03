"""``crypto_news_ticker.js`` against ``crypto_news_ticker_surface.py``,
run in QJSEngine and drawn in QWebEngineView."""

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
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import crypto_news_ticker_surface as cts
from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import theme_engine_surface as tes
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    drain_events,
    js_literals,
    new_engine,
    swap_module,
)

MODULE_PATH = REPO_ROOT / "src" / "gui" / "web" / "crypto_news_ticker.js"
TOKENS_PATH = REPO_ROOT / "src" / "gui" / "web" / "design_tokens.js"
THEMES_PATH = REPO_ROOT / "src" / "gui" / "web" / "theme_engine.js"
WIDGETS_PATH = REPO_ROOT / "src" / "gui" / "web" / "shared_widgets.js"
HEADER_PATH = REPO_ROOT / "src" / "gui" / "web" / "header_strip.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

LOCK_PATH = Path(tempfile.gettempdir()) / "acervator_crypto_news_ticker_swap.lock"
LOCK_ATTEMPTS = 400_000


@contextlib.contextmanager
def module_held(attempts: int = LOCK_ATTEMPTS):
    """Holds one lock file so one worker at a time reads or swaps the module."""
    handle = None
    for _ in range(attempts):
        # Windows answers a file pending deletion with a permission error,
        # not an exists error.
        try:
            handle = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            break
        except (FileExistsError, PermissionError):
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

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 2
HOST_WIDTH_CSS = "480px"

#: Each Python type, and the JavaScript string naming the kind it becomes.
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

FIXED_NOW = 7.0


def story(at: int) -> cts.NewsHeadline:
    feed = cts.NEWS_SOURCES[at % len(cts.NEWS_SOURCES)]
    return cts.NewsHeadline(
        title=f"story number {at}",
        url=f"https://ex.invalid/{at}",
        source=feed,
        published_ts=float(at),
    )


def stories(count: int) -> list:
    return [story(at) for at in range(count)]


def build_state(name: str) -> cts.CryptoNewsTickerModel:
    """One strip in the state ``name``, built by driving the real model."""
    model = cts.CryptoNewsTickerModel(clock=lambda: FIXED_NOW)
    if name == "no_feeds":
        model.on_headlines([])
    elif name == "unavailable":
        model.on_fetch_failed("the feeds refused")
    elif name == "one":
        model.on_headlines(stories(1))
    elif name == "many":
        model.on_headlines(stories(4))
    elif name == "advanced":
        model.on_headlines(stories(4))
        model.advance()
        model.advance()
    elif name == "wrapped":
        model.on_headlines(stories(2))
        model.advance()
        model.advance()
    elif name == "paused":
        model.on_headlines(stories(3))
        model.handle_event(cts.EVENT_ENTER)
        model.advance()
    elif name == "running":
        model.on_headlines(stories(3))
        model.start()
    elif name == "stopped":
        model.on_headlines(stories(3))
        model.start()
        model.stop()
    elif name == "clicked":
        model.on_headlines(stories(3))
        model.handle_event(cts.EVENT_MOUSE_RELEASE)
    return model


STATE_NAMES = (
    "fresh",
    "no_feeds",
    "unavailable",
    "one",
    "many",
    "advanced",
    "wrapped",
    "paused",
    "running",
    "stopped",
    "clicked",
)


def state_payload(name: str) -> dict:
    answer = cts.build_view_model(build_state(name))
    return json.loads(json.dumps(answer, ensure_ascii=True))


def token_payload() -> dict:
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


def theme_payload() -> dict:
    return json.loads(json.dumps(tes.view_model({}), ensure_ascii=True))


class JsRuntime(JsEngine):

    module_path = MODULE_PATH
    setter = "acervatorSetTicker"

    def load_merged(self) -> None:
        """Puts the token, theme, widget and header modules in beside this one."""
        self.run(TOKENS_PATH.read_text(encoding="utf-8"))
        self.run(THEMES_PATH.read_text(encoding="utf-8"))
        self.run(WIDGETS_PATH.read_text(encoding="utf-8"))
        self.run(HEADER_PATH.read_text(encoding="utf-8"))
        self.bind_json("TOKENS", token_payload())
        self.bind_json("THEMES", theme_payload())
        self.run("acervatorSetTokens(JSON.parse(TOKENS));")
        self.run("acervatorSetThemes(JSON.parse(THEMES));")

    def named(self, api: str, name: Any) -> Any:
        self.bind_json("NAME", name)
        return self.json("acervatorTicker." + api + "(JSON.parse(NAME))")

    def push_mutated(self, payload: dict, mutation: str) -> dict:
        self.bind_json("PAYLOAD", payload)
        return self.json(
            "(function () { var model = JSON.parse(PAYLOAD); "
            + mutation
            + " return acervatorSetTicker(model); })()"
        )


@pytest.fixture()
def bare(qapp) -> JsRuntime:
    """The module alone, with no token or header module beside it."""
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


@pytest.fixture()
def js(bare: JsRuntime) -> JsRuntime:
    """The module with the four merged modules loaded beside it."""
    bare.load_merged()
    return bare


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, state: str
):
    """A field the module never names is a value that stops at the bridge."""
    payload = state_payload(state)
    js.push(payload)
    declared = js.json("acervatorTicker.declaredNames()")
    missing = sorted(set(payload) - set(declared))
    assert not missing, f"{len(missing)} published fields have no name: {missing}"
    extra = sorted(set(declared) - set(payload))
    assert not extra, f"the module names fields the surface has none of: {extra}"
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
    payload = dict(state_payload("many"))
    payload["written_only_on_the_surface"] = []
    js.push(payload)
    declared = js.json("acervatorTicker.declaredNames()")
    assert sorted(set(payload) - set(declared)) == ["written_only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_names(js: JsRuntime):
    payload = dict(state_payload("many"))
    del payload["label_text"]
    js.push(payload)
    declared = js.json("acervatorTicker.declaredNames()")
    assert sorted(set(declared) - set(payload)) == ["label_text"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_both_counts_agree_in_every_state(js: JsRuntime, state: str):
    """Declared against held, for the fields, the stories, the feeds and
    the two waits."""
    payload = state_payload(state)
    report = js.push(payload)
    assert report["declared"] == report["held"], f"{state}: {report}"
    assert report["held"]["headlines"] == len(payload["headlines"])
    assert report["held"]["sources"] == len(payload["sources"])
    assert report["held"]["timers"] == payload["timer_count"]


def test_the_count_check_sees_one_story_that_is_not_a_bag(js: JsRuntime):
    payload = state_payload("many")
    payload["headlines"][1] = "a story that is only words"
    report = js.push(payload)
    assert report["declared"]["headlines"] != report["held"]["headlines"]


def test_a_payload_that_is_not_a_bag_draws_nothing_and_is_named(bare: JsRuntime):
    bare.bind_json("PAYLOAD", ["not a bag"])
    report = bare.json("acervatorSetTicker(JSON.parse(PAYLOAD))")
    assert report["declared"] is None
    assert report["faults"] == [
        {"where": None, "field": None, "fault": "not-an-object", "detail": "object"}
    ]
    assert bare.json("acervatorTicker.isLoaded()") is False


@pytest.mark.parametrize("state", STATE_NAMES)
def test_no_shipped_state_is_named_by_any_check(js: JsRuntime, state: str):
    report = js.push(state_payload(state))
    assert report["faults"] == [], f"{state} was named: {report['faults']}"


#: The fields whose values the strip draws, styles with or lays out by.
PAINTED_FIELDS = (
    "accessible_name",
    "cycle_interval_ms",
    "fetches_started",
    "headline_tooltip_format",
    "headlines",
    "index",
    "initial_text",
    "label_stretch",
    "label_style",
    "label_text",
    "label_tooltip",
    "last_refresh_ts",
    "layout_margins",
    "layout_spacing",
    "no_feeds_text",
    "position_format",
    "refresh_interval_ms",
    "source_join",
    "sources",
    "style_sheet",
    "thread_count",
    "timer_count",
    "unavailable_text",
)


def surface_values() -> set:
    """Every value any state of the surface paints, printed."""
    found: set = set()

    def descend(value: Any) -> None:
        if isinstance(value, dict):
            for one in value.values():
                descend(one)
            return
        if isinstance(value, (list, tuple)):
            for one in value:
                descend(one)
            return
        if isinstance(value, bool) or value is None:
            return
        found.add(str(value))

    for name in STATE_NAMES:
        payload = state_payload(name)
        for field in PAINTED_FIELDS:
            descend(payload[field])
    found.discard("")
    return found


def token_values() -> set:
    found: set = set()
    for value in token_payload()["tokens"].values():
        if value is not None:
            found.add(str(value))
    return found


def published_strings() -> set:
    """Every string any state of the surface publishes, name or value."""
    found: set = set()

    def descend(value: Any) -> None:
        if isinstance(value, dict):
            for name, one in value.items():
                found.add(name)
                descend(one)
            return
        if isinstance(value, (list, tuple)):
            for one in value:
                descend(one)
            return
        if isinstance(value, str):
            found.add(value)

    for name in STATE_NAMES:
        descend(state_payload(name))
    found.discard("")
    return found


SURFACE_VALUES = surface_values()
TOKEN_VALUES = token_values()
PUBLISHED_STRINGS = published_strings()
MODULE_LITERALS = js_literals(MODULE_SOURCE)

#: Every published string the module writes, each one a name.
NAMED_WORDS = sorted(
    {
        "abandoned_log",
        "accept_header",
        "accessible_name",
        "actions",
        "advance",
        "aggregate_log",
        "allowlist_log",
        "at_exit_log",
        "browser_new_tab",
        "budget_spent_log",
        "bus_topics",
        "calls",
        "crypto_news_ticker.state",
        "cycle_interval_ms",
        "cycle_running",
        "cycle_timeout",
        "date_tags",
        "default_timeout_s",
        "display_text",
        "event_enter",
        "event_leave",
        "event_mouse_release",
        "fetch_accept",
        "fetch_budget_s",
        "fetch_failed_log",
        "fetch_poll_s",
        "fetch_stopped_log",
        "fetch_user_agent",
        "fetches_started",
        "headline_tooltip_format",
        "headlines",
        "index",
        "initial_text",
        "item_tags",
        "label_cursor",
        "label_stretch",
        "label_style",
        "label_text",
        "label_text_flags",
        "label_tooltip",
        "last_refresh_ts",
        "layout_margins",
        "layout_spacing",
        "link_href",
        "link_tags",
        "live_workers",
        "logger_name",
        "malformed_feed_log",
        "max_feed_bytes",
        "max_fetch_workers",
        "method",
        "name",
        "namespace_mark",
        "no_feeds_text",
        "no_sources_refusal",
        "no_text",
        "no_timestamp",
        "open_failed_log",
        "opened",
        "oversized_feed_log",
        "parse_limit",
        "paused",
        "per_source_limit",
        "position_format",
        "published_ts",
        "read_budget_log",
        "read_chunk_bytes",
        "read_stopped_log",
        "refresh_interval_ms",
        "refresh_running",
        "refresh_timeout",
        "refused_feed_log",
        "retire_wait_ms",
        "skin",
        "slug",
        "source",
        "source_join",
        "sources",
        "still_running_log",
        "stop_wait_ms",
        "style_sheet",
        "thread_count",
        "timer_count",
        "timer_delays_ms",
        "timers",
        "title",
        "title_max_chars",
        "title_tags",
        "unavailable_text",
        "url",
        "user_agent_header",
        "widget_fetch_failed_log",
        "worker_lifecycle",
        "worker_name",
        "worker_running",
    }
)

#: Every other string the module writes: CSS words, tags and fault words.
OWN_WORDS = sorted(
    {
        "",
        " ",
        " * 1px)",
        "#",
        "%",
        ")",
        ",",
        ", ",
        ".",
        ":",
        ";",
        "<",
        '=\\"',
        "AARRGGBB",
        "[",
        '\\"]',
        "acervator-news-ticker",
        "acervator-news-ticker-line",
        "aria-label",
        "boolean",
        "calc(",
        "call:",
        "center",
        "click",
        "data-action",
        "data-cycle-interval-ms",
        "data-cycle-running",
        "data-fetches-started",
        "data-index",
        "data-last-refresh-ts",
        "data-live-workers",
        "data-part",
        "data-paused",
        "data-published-ts",
        "data-refresh-interval-ms",
        "data-refresh-running",
        "data-slot",
        "data-source",
        "data-thread-count",
        "data-timer-count",
        "data-total",
        "data-url",
        "data-worker-running",
        "disagrees",
        "div",
        "flex",
        "font-size",
        "function",
        "headline",
        "headline:",
        "hidden",
        "hover",
        "markup",
        "missing",
        "news-ticker",
        "not-a-list",
        "not-an-object",
        "not-plain",
        "nowrap",
        "null",
        "number",
        "object",
        "out-of-range",
        "paddingBottom",
        "paddingLeft",
        "paddingRight",
        "paddingTop",
        "pointer",
        "px",
        "qt-colour",
        "rgba(",
        "row",
        "source:",
        "spacing",
        "string",
        "text",
        "the preload bridge is not present",
        "ticker",
        "too-long",
        "type_scale",
        "use strict",
        "var(--",
        "wrong-type",
    }
)


def test_the_module_writes_no_number():
    assert not MODULE_LITERALS["numbers"], (
        "crypto_news_ticker.js holds numeric literals: " f"{MODULE_LITERALS['numbers']}"
    )


def test_the_module_writes_no_colour():
    """A colour typed here drifts from the surface the next time the strip
    is repainted, and nothing reports the drift."""
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"crypto_news_ticker.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_strip_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & SURFACE_VALUES)
    assert not written, f"crypto_news_ticker.js spells out strip values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"crypto_news_ticker.js spells out token values: {written}"


def test_the_module_names_only_the_surface_words_it_must_read():
    written = sorted(set(MODULE_LITERALS["strings"]) & PUBLISHED_STRINGS)
    assert written == NAMED_WORDS, (
        f"the module names {sorted(set(written) - set(NAMED_WORDS))} more and "
        f"{sorted(set(NAMED_WORDS) - set(written))} fewer published strings "
        "than the list allows"
    )


def test_every_string_the_module_writes_is_listed():
    """Nothing the module spells out escapes both lists, so a value added
    later cannot arrive unnamed."""
    written = sorted(set(MODULE_LITERALS["strings"]))
    assert written == sorted(set(NAMED_WORDS) | set(OWN_WORDS))


def test_every_listed_word_is_a_name_and_not_a_value_the_strip_shows():
    overlap = sorted((set(NAMED_WORDS) | set(OWN_WORDS)) & SURFACE_VALUES)
    assert not overlap, f"these listed words are values the strip paints: {overlap}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        "crypto_news_ticker.js holds a slash outside a comment, which the "
        f"literal scan cannot read: {MODULE_LITERALS['slashes']}"
    )


WRITTEN_LINES = {
    "colour": 'var written = "' + cts.LABEL_STYLE + '";',
    "cycle_wait": "var written = " + str(cts.CYCLE_INTERVAL_MS) + ";",
    "initial_text": 'var written = "' + cts.INITIAL_TEXT + '";',
    "accessible_name": 'var written = "' + cts.ACCESSIBLE_NAME + '";',
    "feed_address": 'var written = "' + cts.NEWS_SOURCES[0].url + '";',
    "join": 'var written = "' + cts.SOURCE_JOIN + '";',
    "token_value": 'var written = "' + str(dss.PRIMARY) + '";',
    "regex": "var written = /ab+c/;",
}


def caught_by_scan(source: str) -> set:
    """Which of the checks above report on ``source``."""
    found = js_literals(source)
    strings = set(found["strings"])
    caught = set()
    if found["numbers"]:
        caught.add("number")
    if HEX_COLOUR.findall(source):
        caught.add("colour")
    if strings & SURFACE_VALUES:
        caught.add("surface_value")
    if strings & TOKEN_VALUES:
        caught.add("token_value")
    if found["slashes"]:
        caught.add("regex")
    return caught


@pytest.mark.parametrize("kind", sorted(WRITTEN_LINES))
def test_the_literal_scan_names_one_written_value(kind: str):
    caught = caught_by_scan(WRITTEN_LINES[kind])
    assert caught, f"the scan reported nothing on the written {kind}"


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    found = js_literals('// #00ffcc\nvar kept = "kept";')
    assert found["strings"] == ["kept"]
    assert not found["numbers"]


def scan_each_written_value() -> tuple:
    """Appends each written line to the module and scans the file back."""
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
            assert after == before, f"the file was not restored after {kind}"
    finally:
        swap_module(MODULE_PATH, original)
    return caught_each, before


def test_each_written_value_is_caught_in_the_module_file_itself():
    with module_held():
        caught_each, before = scan_each_written_value()
    unseen = sorted(kind for kind, caught in caught_each.items() if not caught)
    assert not unseen, f"the scan reported nothing on these lines: {unseen}"
    assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before


def test_the_module_swap_reports_when_every_attempt_is_used_up():
    with module_held():
        original = MODULE_PATH.read_bytes()
        with pytest.raises(AssertionError) as raised:
            swap_module(MODULE_PATH, original, attempts=0)
        assert MODULE_PATH.name in str(raised.value)
        assert MODULE_PATH.read_bytes() == original


def test_the_module_lock_refuses_a_second_taker():
    with module_held():
        with pytest.raises(AssertionError) as raised:
            with module_held(attempts=1):
                raise AssertionError("the second taker was let in")
        assert LOCK_PATH.name in str(raised.value)
    with module_held():
        assert LOCK_PATH.exists()


def test_the_written_file_is_still_a_module_the_page_can_run(bare: JsRuntime):
    for kind, line in sorted(WRITTEN_LINES.items()):
        runtime = JsRuntime(bare.engine_of(), MODULE_SOURCE + line)
        assert runtime.json("typeof acervatorSetTicker") == "function", kind


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
    expected = python_kinds(payload)
    actual = js.json("acervatorTicker.kinds()")
    differing = {
        path: (kind, actual.get(path))
        for path, kind in expected.items()
        if actual.get(path) != kind
    }
    assert not differing, (
        f"{state}: {len(differing)} of {len(expected)} values changed "
        f"type: {sorted(differing)}"
    )
    assert sorted(actual) == sorted(expected)


def test_the_type_check_names_one_value_that_changed_shape(js: JsRuntime):
    payload = state_payload("many")
    payload["index"] = str(payload["index"])
    js.push(payload)
    assert js.json("acervatorTicker.kinds()")["index"] == "string"
    assert python_kinds(state_payload("many"))["index"] == "number"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_payload_value_is_data_a_json_line_can_hold(js: JsRuntime, state: str):
    js.push(state_payload(state))
    assert js.json("acervatorTicker.plainness()") == []


def test_the_plain_data_walk_names_a_live_object_hidden_under_a_story(js: JsRuntime):
    report = js.push_mutated(
        state_payload("many"), "model.headlines[1].source = new Date();"
    )
    named = [f for f in report["faults"] if f["fault"] == "not-plain"]
    assert [f["field"] for f in named] == ["headlines.1.source"]


def test_the_plain_data_walk_names_a_function_at_the_top(js: JsRuntime):
    report = js.push_mutated(
        state_payload("many"), "model.label_text = function () { return 1; };"
    )
    named = [f for f in report["faults"] if f["fault"] == "not-plain"]
    assert [f["field"] for f in named] == ["label_text"]


def test_the_plain_data_walk_lets_every_scalar_and_null_through(js: JsRuntime):
    report = js.push_mutated(
        state_payload("many"),
        "model.headlines[0].published_ts = null;"
        " model.headlines[1].title = 0;"
        " model.paused = false;",
    )
    named = [f for f in report["faults"] if f["fault"] == "not-plain"]
    assert named == [], f"a scalar or a null was named as a live object: {named}"


class Browser:
    """The real renderer page, loaded from disk in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        self.open_page()
        self.wait_for_module()

    def open_page(self) -> None:
        """Loads INDEX_HTML from disk and waits for the load to finish."""
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
        """Spins for the module, opening the page again once it is absent."""
        for attempt in range(PAGE_ATTEMPTS):
            if attempt:
                self.open_page()
            for _ in range(READY_ROUNDS):
                if self.js("typeof window.acervatorSetTicker") == "function":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the ticker module: readyState "
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
    """The page, or a skip when Chromium is not installed with Qt."""
    assert qapp is not None
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    page = Browser()
    yield page
    page.close()


#: Every computed style name read off a drawn part, cursor included.
STYLE_NAMES = [
    "display",
    "flexDirection",
    "alignItems",
    "flexGrow",
    "columnGap",
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "color",
    "fontSize",
    "whiteSpace",
    "overflowX",
    "cursor",
    "userSelect",
]

#: Each Qt sheet property, expanded into the computed colour and font names.
EXPANDED = {"color": ("color",), "font-size": ("fontSize",)}

PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = " + json.dumps(HOST_WIDTH_CSS) + ";"
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
    "      var own = '';"
    "      Array.prototype.slice.call(el.childNodes).forEach(function (n) {"
    "        if (n.nodeType === Node.TEXT_NODE) { own += n.nodeValue; } });"
    "      found.push({ path: here, tag: el.tagName, attrs: attrs,"
    "        width: el.clientWidth, room: el.scrollWidth, text: own,"
    "        html: el.innerHTML, children: el.children.length,"
    "        style: window.readStyle(el, names) });"
    "    }"
    "    Array.prototype.slice.call(el.children).forEach(function (child) {"
    "      walk(child, here); });"
    "  };"
    "  if (window.HOST.firstChild) { walk(window.HOST.firstChild, ''); }"
    "  return JSON.stringify(found); })()"
)


def give_tokens(browser: Browser) -> int:
    """Puts the real token table on the page and into its CSS."""
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    written = browser.parsed(
        "(function () {"
        "  acervatorSetTokens(JSON.parse(window.TOKENS));"
        "  return acervatorTokens.apply(document.documentElement); })()"
    )
    assert written, "no design token reached the page's stylesheet"
    return len(written)


#: A page nobody shows throttles its own waits, so the ask is waited for.
ASK_ROUNDS = 40


def wait_for_asks(browser: Browser) -> list:
    """Spins until both waits have asked once, or the rounds run out."""
    sent: list = []
    for _ in range(ASK_ROUNDS):
        browser.settle(READY_STEP_MS)
        sent = browser.parsed("window.SENT")
        if len(sent) > 1:
            return sent
    return sent


def draw_ticker(browser: Browser, payload: dict) -> list:
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetTicker(JSON.parse(window.PAYLOAD));"
        "acervatorTicker.renderTicker(window.HOST);"
    )
    return json.loads(browser.js(READ_PARTS))


def part_named(drawn: list, path: str) -> dict:
    found = [one for one in drawn if one["path"] == path]
    assert len(found) == 1, f"{path} was drawn {len(found)} times"
    return found[0]


def probe(browser: Browser, body: str) -> dict:
    """The computed values a bare element takes from the same label style."""
    names: list = []
    for one in cts.LABEL_STYLE.split(";"):
        property_name = one.split(":")[0].strip()
        names.extend(EXPANDED.get(property_name, ()))
    browser.js("window.PROBE_NAMES = " + json.dumps(json.dumps(names)) + ";")
    return browser.parsed(
        "window.probeStyle(" + json.dumps(body) + ", JSON.parse(window.PROBE_NAMES))"
    )


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_page_draws_the_words_the_surface_put_on_the_strip(
    browser: Browser, state: str
):
    payload = state_payload(state)
    drawn = draw_ticker(browser, payload)
    assert part_named(drawn, "ticker/headline")["text"] == payload["label_text"]


def test_the_drawn_word_check_reads_a_different_word_for_a_different_state(
    browser: Browser,
):
    one = draw_ticker(browser, state_payload("many"))
    other = draw_ticker(browser, state_payload("advanced"))
    assert (
        part_named(one, "ticker/headline")["text"]
        != part_named(other, "ticker/headline")["text"]
    )


def test_every_element_the_page_draws_carries_a_name_a_check_reads(browser: Browser):
    draw_ticker(browser, state_payload("many"))
    every = browser.js("window.HOST.querySelectorAll('*').length")
    named = browser.js("window.HOST.querySelectorAll('[data-part]').length")
    assert every == named, f"{every - named} drawn elements carry no name"
    assert named


def test_the_named_element_check_sees_an_element_carrying_no_name(browser: Browser):
    draw_ticker(browser, state_payload("many"))
    browser.js("window.HOST.firstChild.appendChild(document.createElement('span'));")
    every = browser.js("window.HOST.querySelectorAll('*').length")
    named = browser.js("window.HOST.querySelectorAll('[data-part]').length")
    assert every - named == 1


def test_the_strip_takes_its_two_margins_from_the_layout_the_surface_publishes(
    browser: Browser,
):
    payload = state_payload("many")
    drawn = draw_ticker(browser, payload)
    style = part_named(drawn, "ticker")["style"]
    wanted = browser.parsed(
        "window.probeStyle('padding: "
        + "px ".join(str(payload["layout_margins"][at]) for at in (1, 2, 3, 0))
        + "px', ['paddingLeft', 'paddingTop', 'paddingRight', 'paddingBottom'])"
    )
    assert {name: style[name] for name in wanted} == wanted


def test_the_margin_check_reads_a_different_padding_for_a_different_number(
    browser: Browser,
):
    payload = state_payload("many")
    payload["layout_margins"] = [21, 22, 23, 24]
    drawn = draw_ticker(browser, payload)
    style = part_named(drawn, "ticker")["style"]
    assert style["paddingLeft"] == "21px"
    assert style["paddingBottom"] == "24px"


def test_the_headline_takes_the_whole_sheet_the_surface_publishes(browser: Browser):
    """Read off the document against a probe built from the declaration, not
    from a typed number."""
    payload = state_payload("many")
    drawn = draw_ticker(browser, payload)
    style = part_named(drawn, "ticker/headline")["style"]
    wanted = probe(browser, payload["label_style"])
    assert {name: style[name] for name in wanted} == wanted


def test_the_sheet_check_reads_a_different_value_for_a_different_sheet(
    browser: Browser,
):
    payload = state_payload("many")
    drawn = draw_ticker(browser, payload)
    style = part_named(drawn, "ticker/headline")["style"]
    other = probe(browser, "color: #ff0000; font-size: 33px;")
    assert {name: style[name] for name in other} != other


def test_the_font_size_is_painted_through_the_one_token_that_carries_it(
    browser: Browser,
):
    payload = state_payload("many")
    draw_ticker(browser, payload)
    browser.js("window.SHEET = " + json.dumps(payload["label_style"]) + ";")
    kept = browser.js("acervatorTicker.keptSheet(window.SHEET)")
    assert "var(--TYPE_SMALL" in kept, kept


def test_the_colour_the_strip_paints_is_carried_by_no_design_token(browser: Browser):
    """One of this strip's two style values resolves to a token and one
    does not."""
    payload = state_payload("many")
    draw_ticker(browser, payload)
    browser.js("window.COLOUR = " + json.dumps(cts.LABEL_STYLE) + ";")
    named = browser.js(
        "String(acervatorTicker.variableFor("
        "window.COLOUR.split(':')[1].split(';')[0].trim()))"
    )
    assert named == "undefined", f"a token now carries the strip's colour: {named}"
    browser.js("window.SIZE = " + json.dumps(11) + ";")
    assert (
        browser.js("String(acervatorTicker.variableFor(window.SIZE))") == "TYPE_SMALL"
    )


def test_the_headline_carries_the_pointer_and_the_selection_qt_gives_it(
    browser: Browser,
):
    drawn = draw_ticker(browser, state_payload("many"))
    style = part_named(drawn, "ticker/headline")["style"]
    assert style["cursor"] == "pointer"
    assert style["userSelect"] == "text"
    assert style["whiteSpace"] == "nowrap"
    assert style["overflowX"] == "hidden"


def test_the_pointer_check_sees_a_cursor_name_the_module_maps_to_nothing(
    browser: Browser,
):
    payload = state_payload("many")
    payload["label_cursor"] = "WhatsThisCursor"
    payload["label_text_flags"] = "NoTextInteraction"
    drawn = draw_ticker(browser, payload)
    style = part_named(drawn, "ticker/headline")["style"]
    assert style["cursor"] != "pointer"
    assert style["userSelect"] != "text"


def test_the_page_writes_markup_in_a_feed_title_as_words_and_draws_no_child(
    browser: Browser,
):
    """A QLabel reads a feed title as rich text; React writes it as words."""
    model = build_state("one")
    model.headlines[0].title = '<b>bold</b> and <img src="http://x.invalid/p.png">'
    model.render_current()
    payload = json.loads(json.dumps(cts.build_view_model(model), ensure_ascii=True))
    drawn = draw_ticker(browser, payload)
    line = part_named(drawn, "ticker/headline")
    assert line["children"] == 0, f"React drew an element from markup: {line['html']}"
    assert "<b>" not in line["html"]
    assert "&lt;b&gt;" in line["html"]
    assert line["text"] == payload["label_text"]


def test_the_markup_check_sees_a_child_element_when_one_is_really_drawn(
    browser: Browser,
):
    draw_ticker(browser, state_payload("one"))
    browser.js(
        "window.HOST.querySelector('[data-part=\"headline\"]')"
        ".innerHTML = '<b>bold</b>';"
    )
    drawn = json.loads(browser.js(READ_PARTS))
    assert part_named(drawn, "ticker/headline")["children"] == 1


def test_the_page_draws_a_headline_carrying_a_web_address_as_words(
    browser: Browser,
):
    model = build_state("one")
    model.headlines[0].title = "read it at https://example.invalid/story"
    model.render_current()
    payload = json.loads(json.dumps(cts.build_view_model(model), ensure_ascii=True))
    drawn = draw_ticker(browser, payload)
    line = part_named(drawn, "ticker/headline")
    assert line["children"] == 0
    assert "<a" not in line["html"]
    assert "https://example.invalid/story" in line["text"]


def test_the_page_draws_no_element_for_a_payload_that_is_not_a_bag(browser: Browser):
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    browser.js(
        "acervatorTicker.forget();"
        "acervatorTicker.renderTicker(window.HOST, 'not a bag');"
    )
    assert browser.js("window.HOST.querySelectorAll('[data-part]').length") == 0


def test_the_module_fills_the_space_the_exchange_screen_leaves_for_it(
    browser: Browser,
):
    """The parent screen leaves a space named `news-ticker`; mount finds it."""
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js(
        "window.HOST.innerHTML = '';"
        "var space = document.createElement('div');"
        "space.setAttribute('data-slot', acervatorTicker.slot);"
        "window.HOST.appendChild(space);"
    )
    browser.js(
        "window.PAYLOAD = " + json.dumps(json.dumps(state_payload("many"))) + ";"
    )
    filled = browser.js(
        "(function () {"
        "  acervatorSetTicker(JSON.parse(window.PAYLOAD));"
        "  acervatorTicker.mount(window.HOST);"
        "  return window.HOST.querySelectorAll('[data-part=\"ticker\"]').length; })()"
    )
    assert filled == 1


def test_the_mount_check_finds_no_space_when_the_screen_leaves_none(
    browser: Browser,
):
    browser.js(PAGE_HELPERS)
    browser.js("window.HOST.innerHTML = '';")
    assert browser.parsed("acervatorTicker.mount(window.HOST)") is None


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_sequence_of_stories_keeps_the_order_the_surface_sent(
    js: JsRuntime, state: str
):
    """A ticker is a sequence, so its order is read by address and not by
    place."""
    payload = state_payload(state)
    js.push(payload)
    assert js.json("acervatorTicker.headlineOrder()") == [
        one["url"] for one in payload["headlines"]
    ]


def test_the_story_order_check_sees_two_stories_swapped(js: JsRuntime):
    payload = state_payload("many")
    payload["headlines"][0], payload["headlines"][3] = (
        payload["headlines"][3],
        payload["headlines"][0],
    )
    js.push(payload)
    assert js.json("acervatorTicker.headlineOrder()") != [
        one["url"] for one in state_payload("many")["headlines"]
    ]


def test_the_ten_feeds_keep_the_order_the_surface_sent(js: JsRuntime):
    js.push(state_payload("many"))
    assert js.json("acervatorTicker.sourceOrder()") == [
        one.slug for one in cts.NEWS_SOURCES
    ]


def test_the_two_waits_keep_the_order_the_surface_sent(js: JsRuntime):
    payload = state_payload("running")
    js.push(payload)
    assert js.json("acervatorTicker.timerNames()") == list(payload["timers"])
    assert [payload["timers"][name] for name in payload["timers"]] == payload[
        "timer_delays_ms"
    ]


def test_the_wait_order_check_names_a_bag_that_disagrees_with_its_list(
    js: JsRuntime,
):
    payload = state_payload("running")
    payload["timer_delays_ms"] = list(reversed(payload["timer_delays_ms"]))
    report = js.push(payload)
    assert any(f["field"] == "timer_delays_ms" for f in report["faults"])


def test_the_steps_the_strip_recorded_keep_their_order(js: JsRuntime):
    payload = state_payload("running")
    js.push(payload)
    assert js.json("acervatorTicker.callOrder()") == [
        one[0] for one in payload["calls"]
    ]


def test_the_seven_handler_names_keep_the_order_the_surface_sent(js: JsRuntime):
    payload = state_payload("many")
    js.push(payload)
    assert js.json("acervatorTicker.actionOrder()") == list(payload["actions"])
    assert js.json("acervatorTicker.workerNames()") == list(payload["worker_lifecycle"])


@pytest.mark.parametrize("state", ("one", "many", "advanced", "wrapped", "paused"))
def test_the_story_on_the_strip_is_the_one_the_place_names(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    assert (
        js.json("acervatorTicker.current()") == payload["headlines"][payload["index"]]
    )


def test_the_current_story_check_sees_the_place_move(js: JsRuntime):
    js.push(state_payload("many"))
    first = js.json("acervatorTicker.current()")["url"]
    js.push(state_payload("advanced"))
    assert js.json("acervatorTicker.current()")["url"] != first


def test_the_place_wraps_back_to_the_first_story(js: JsRuntime):
    payload = state_payload("wrapped")
    assert payload["index"] == 0
    assert payload["label_text"].endswith(payload["headlines"][0]["display_text"])


HANDLERS = {
    "advance": ("cycle_timeout", {"advance": 1}),
    "refresh": ("refresh_timeout", {}),
    "hover": (None, {"hover": True}),
    "release": (None, {"hover": False}),
    "openStory": (None, {"click": True}),
}

EVENT_FIELD = {
    "hover": "event_enter",
    "release": "event_leave",
    "openStory": "event_mouse_release",
}


@pytest.mark.parametrize("handler", sorted(HANDLERS))
def test_each_handler_asks_the_bridge_with_the_argument_the_surface_names(
    js: JsRuntime, handler: str
):
    payload = state_payload("running")
    js.push(payload)
    js.run("acervatorTicker." + handler + "();")
    sent = js.json("acervatorTicker.sent()")
    assert len(sent) == 1, f"{handler} asked {len(sent)} times"
    action, params = HANDLERS[handler]
    wanted = payload["actions"][action] if action else payload[EVENT_FIELD[handler]]
    assert sent[0] == {"event": wanted, "params": params}


def test_the_handler_check_sees_a_handler_that_asks_for_nothing(js: JsRuntime):
    js.push(state_payload("running"))
    assert js.json("acervatorTicker.sent()") == []


def test_the_two_waits_run_the_advance_and_the_refresh_the_surface_names(
    browser: Browser,
):
    """Qt moves the strip with a timer, so the page moves it with the same
    two waits."""
    payload = state_payload("running")
    payload["cycle_interval_ms"] = 20
    payload["refresh_interval_ms"] = 20
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "window.SENT = [];"
        "window.acervator = { call: function (m, p) {"
        "  window.SENT.push(p); return Promise.resolve(null); } };"
        "acervatorTicker.forget();"
        "acervatorSetTicker(JSON.parse(window.PAYLOAD));"
        "acervatorTicker.renderTicker(window.HOST);"
    )
    sent = wait_for_asks(browser)
    browser.js("delete window.acervator;")
    assert any("advance" in one for one in sent), sent
    assert any(one == {} for one in sent), sent


def test_the_waits_do_not_run_when_the_surface_says_both_are_stopped(
    browser: Browser,
):
    payload = state_payload("stopped")
    payload["cycle_interval_ms"] = 20
    payload["refresh_interval_ms"] = 20
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "window.SENT = [];"
        "window.acervator = { call: function (m, p) {"
        "  window.SENT.push(p); return Promise.resolve(null); } };"
        "acervatorTicker.forget();"
        "acervatorSetTicker(JSON.parse(window.PAYLOAD));"
        "acervatorTicker.renderTicker(window.HOST);"
    )
    sent = wait_for_asks(browser)
    browser.js("delete window.acervator;")
    assert sent == [], f"a stopped strip still moved: {sent}"


def test_a_click_on_the_drawn_headline_asks_the_bridge_to_open_the_story(
    browser: Browser,
):
    payload = state_payload("many")
    draw_ticker(browser, payload)
    sent = browser.parsed(
        "(function () {"
        "  window.SENT = [];"
        "  window.acervator = { call: function (m, p) {"
        "    window.SENT.push(p); return Promise.resolve(null); } };"
        "  window.HOST.querySelector('[data-part=\"headline\"]').click();"
        "  delete window.acervator;"
        "  return window.SENT; })()"
    )
    assert sent == [{"click": True}]


def test_the_click_check_sees_nothing_sent_when_no_click_happens(browser: Browser):
    draw_ticker(browser, state_payload("many"))
    sent = browser.parsed(
        "(function () {"
        "  window.SENT = [];"
        "  window.acervator = { call: function (m, p) {"
        "    window.SENT.push(p); return Promise.resolve(null); } };"
        "  delete window.acervator;"
        "  return window.SENT; })()"
    )
    assert sent == []


def test_the_module_asks_the_bridge_once_and_names_a_page_that_has_none(
    js: JsRuntime,
):
    assert js.json("acervatorTicker.isLoaded()") is False
    js.run("acervatorLoadTicker({});")
    drain_events()
    assert js.json("acervatorTicker.loadError()") == "the preload bridge is not present"


def test_the_module_takes_the_state_a_bridge_answers_with(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload("many"))
    js.run(
        "window.acervator = { call: function () {"
        "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
        "acervatorLoadTicker({});"
    )
    drain_events()
    assert js.json("acervatorTicker.isLoaded()") is True
    assert js.json("acervatorTicker.loadError()") is None


#: Every hostile value, and the JavaScript that writes it into the strip.
HOSTILE_STORIES = {
    "no title": "delete model.headlines[0].title;",
    "a null title": "model.headlines[0].title = null;",
    "a number where a title belongs": "model.headlines[0].title = 12;",
    "text where a stamp belongs": "model.headlines[0].published_ts = '12';",
    "not a number": "model.headlines[0].published_ts = NaN;",
    "an infinity": "model.headlines[0].published_ts = Infinity;",
    "a negative infinity": "model.headlines[0].published_ts = -Infinity;",
    "a very large integer": "model.headlines[0].published_ts = 1e24;",
    "no feed": "delete model.headlines[0].source;",
    "a null feed": "model.headlines[0].source = null;",
    "a story that is only words": "model.headlines[0] = 'a story';",
    "a story that is null": "model.headlines[0] = null;",
    "a two hundred letter headline": "model.headlines[0].title = new Array(201).join('M');",
    "markup in a headline": "model.headlines[0].title = '<img src=\"x\">';",
    "a newline in a headline": "model.headlines[0].title = 'one\\ntwo';",
    "a web address in a headline": "model.headlines[0].title = 'see https://ex.invalid/a';",
    "a duplicate headline": "model.headlines[1] = model.headlines[0];",
    "an empty feed list": "model.headlines = [];",
    "stories that are not a list": "model.headlines = 'stories';",
    "a place past the last story": "model.index = 9;",
    "a place that is text": "model.index = 'first';",
}

#: The hostile values the module must name, and the fault it must name them with.
HOSTILE_NAMED = {
    "no title": "missing",
    "a null title": "wrong-type",
    "a number where a title belongs": "wrong-type",
    "text where a stamp belongs": "wrong-type",
    "not a number": "wrong-type",
    "an infinity": "wrong-type",
    "a negative infinity": "wrong-type",
    "no feed": "not-an-object",
    "a null feed": "not-an-object",
    "a story that is only words": "not-an-object",
    "a story that is null": "not-an-object",
    "a two hundred letter headline": "disagrees",
    "markup in a headline": "markup",
    "stories that are not a list": "not-a-list",
    "a place past the last story": "out-of-range",
    "a place that is text": "wrong-type",
}


@pytest.mark.parametrize("case", sorted(HOSTILE_STORIES))
def test_a_hostile_value_leaves_the_module_answering_and_the_strip_drawable(
    js: JsRuntime, case: str
):
    """Every hostile value is carried as it arrived, never thrown."""
    report = js.push_mutated(state_payload("many"), HOSTILE_STORIES[case])
    assert isinstance(report["faults"], list)
    assert js.json("acervatorTicker.isLoaded()") is True
    assert isinstance(js.json("acervatorTicker.headlineOrder()"), list)


@pytest.mark.parametrize("case", sorted(HOSTILE_NAMED))
def test_a_hostile_value_the_module_must_name_is_named(js: JsRuntime, case: str):
    report = js.push_mutated(state_payload("many"), HOSTILE_STORIES[case])
    named = [f["fault"] for f in report["faults"]]
    assert HOSTILE_NAMED[case] in named, f"{case}: the module named {named}"


def test_the_hostile_value_check_is_quiet_on_a_shipped_payload(js: JsRuntime):
    report = js.push(state_payload("many"))
    assert report["faults"] == []


def test_an_empty_feed_leaves_the_strip_on_the_words_the_surface_publishes(
    js: JsRuntime,
):
    payload = state_payload("no_feeds")
    js.push(payload)
    assert payload["headlines"] == []
    assert payload["label_text"] == cts.NO_FEEDS_TEXT
    assert js.json("acervatorTicker.headlineOrder()") == []
    assert js.json("acervatorTicker.current()") == {}


def test_a_duplicate_headline_is_drawn_twice_and_named_by_nothing(js: JsRuntime):
    report = js.push_mutated(
        state_payload("many"), HOSTILE_STORIES["a duplicate headline"]
    )
    assert report["faults"] == []
    order = js.json("acervatorTicker.headlineOrder()")
    assert order[0] == order[1]


@pytest.mark.parametrize(
    "field", sorted(("label_text", "headlines", "timers", "index"))
)
def test_a_field_the_payload_omits_is_named_as_missing(js: JsRuntime, field: str):
    payload = state_payload("many")
    del payload[field]
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "missing",
        "detail": None,
    } in report["faults"]


@pytest.mark.parametrize(
    "field", sorted(("label_text", "headlines", "timers", "index"))
)
def test_a_field_carrying_null_is_named(js: JsRuntime, field: str):
    payload = state_payload("many")
    payload[field] = None
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "null",
        "detail": None,
    } in report["faults"]


def test_a_sheet_qt_would_read_as_another_colour_is_refused_and_named(js: JsRuntime):
    """Qt reads eight hex digits as alpha first, CSS reads them as alpha
    last."""
    payload = state_payload("many")
    payload["label_style"] = "color: #80ffd700; font-size: 11px;"
    report = js.push(payload)
    assert {
        "where": "color",
        "field": "label_style",
        "fault": "qt-colour",
        "detail": "AARRGGBB",
    } in report["faults"]
    js.bind_json("SHEET", payload["label_style"])
    assert "color" not in js.json("acervatorTicker.styleOf(JSON.parse(SHEET))")


def test_a_byte_counted_alpha_is_refused_and_named(js: JsRuntime):
    payload = state_payload("many")
    payload["label_style"] = "color: rgba(255, 215, 0, 128);"
    report = js.push(payload)
    assert {
        "where": "color",
        "field": "label_style",
        "fault": "qt-colour",
        "detail": "rgba(",
    } in report["faults"]


def test_the_colour_check_keeps_a_sheet_css_reads_the_same_way(js: JsRuntime):
    payload = state_payload("many")
    report = js.push(payload)
    assert not [f for f in report["faults"] if f["fault"] == "qt-colour"]
    js.bind_json("SHEET", payload["label_style"])
    assert "color" in js.json("acervatorTicker.styleOf(JSON.parse(SHEET))")


def test_a_not_a_number_stamp_cannot_cross_the_bridge_as_json():
    """The bridge writes NaN, which JSON.parse refuses, so this stamp never
    reaches the module on the real page."""
    answer = cts.build_view_model(build_state("one"))
    answer["headlines"][0]["published_ts"] = float("nan")
    written = json.dumps(answer)
    assert "NaN" in written
    with pytest.raises(json.JSONDecodeError):
        json.loads(written, parse_constant=_refuse_constant)


def _refuse_constant(name: str) -> Any:
    raise json.JSONDecodeError("JSON.parse refuses " + name, name, 0)


def test_the_page_names_this_module_once_and_after_the_ones_it_reads():
    html = INDEX_HTML.read_text(encoding="utf-8")
    named = [line for line in html.splitlines() if MODULE_PATH.name in line]
    assert len(named) == 1, f"{MODULE_PATH.name} is named {len(named)} times"
    lines = html.splitlines()
    mine = lines.index(named[0])
    for other in (
        "design_tokens.js",
        "theme_engine.js",
        "shared_widgets.js",
        "header_strip.js",
    ):
        earlier = [at for at, line in enumerate(lines) if other in line]
        assert earlier and earlier[0] < mine, f"{other} is not loaded before mine"


def test_the_script_line_points_at_the_module_this_test_reads():
    html = INDEX_HTML.read_text(encoding="utf-8")
    named = [line for line in html.splitlines() if MODULE_PATH.name in line]
    href = named[0].split('src="')[1].split('"')[0]
    assert (INDEX_HTML.parent / href).resolve() == MODULE_PATH


def test_the_surface_serves_the_method_the_module_asks_for(js: JsRuntime):
    assert js.json("acervatorTicker.method") == cts.METHOD
    assert cts.view_model({"reset": True})["method"] == cts.METHOD
