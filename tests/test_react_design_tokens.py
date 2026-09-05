"""Issue #128 Stage 3 unit 1 -- the React side of the design tokens.

WHAT IS PROVED
==============
``src/gui/web/design_tokens.js`` publishes the token table that
``src/gui/main_tabs/design_system_surface.py`` serves, and carries no
token value of its own. Two sources of truth for one skin is the defect
this unit exists to prevent, so the value agreement and the
no-literals scan are the two halves of the same claim.

HOW THE JAVASCRIPT IS RUN
=========================
Node is not installed and nothing here adds a JavaScript test runner.
Two engines already in the tree run the module instead.
``QJSEngine`` from ``PySide6.QtQml`` -- the engine
``tests/test_desktop_shell_assets.py`` already parses the shell with --
runs it as plain JavaScript and answers in JSON. ``QWebEngineView``
loads the real ``desktop/renderer/index.html`` from disk, which is the
only way to run the module under the page's own content-security
policy.

THE CONTROLS
============
Every count here has a planted opposite that must be named. A token
added to one side alone is named by the reach check. A colour, a number
and a real token value planted in a copy of the source are each named by
the literal scan. A network call from the loaded page is refused with
``connect-src`` in the violation record, which a failed name lookup
could not produce.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import design_system_surface as dss
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    drain_events,
    js_literals,
    new_engine,
)

MODULE_PATH = REPO_ROOT / "src" / "gui" / "web" / "design_tokens.js"
BOOT_PATH = REPO_ROOT / "desktop" / "renderer" / "boot.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

JS_TIMEOUT_MS = 30_000

#: Python type -> the JavaScript type the same value has after `json.dumps`.
JS_TYPE_OF = {
    "str": "string",
    "int": "number",
    "float": "number",
    "tuple": "object",
    "list": "object",
    "NoneType": "null",
}


# -- the surface, as the bridge serialises it --------------------------


def bridge_payload(**params: Any) -> dict:
    """The surface's answer after one round trip through the bridge's JSON.

    ``src/core/desktop_bridge.py`` writes every response with
    ``json.dumps(..., ensure_ascii=True)``, so a tuple reaches the
    renderer as an array. Comparing the module against the raw Python
    dict would charge the module for that conversion.
    """
    return json.loads(json.dumps(dss.view_model(params), ensure_ascii=True))


def scalar_tokens(values: dict) -> dict:
    """The tokens a stylesheet can hold: text and numbers, not arrays."""
    return {
        name: value
        for name, value in values.items()
        if isinstance(value, (str, int, float)) and not isinstance(value, bool)
    }


# -- the JavaScript engine ---------------------------------------------


class JsRuntime(JsEngine):
    """A QJSEngine holding ``design_tokens.js`` and a ``window`` global."""

    module_path = MODULE_PATH
    setter = "acervatorSetTokens"


@pytest.fixture()
def js(qapp) -> JsRuntime:
    """The module, loaded in a fresh engine."""
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_PATH.read_text(encoding="utf-8"))


@pytest.fixture()
def loaded(js: JsRuntime) -> JsRuntime:
    """The module holding the real surface's whole token table."""
    js.push(bridge_payload())
    return js


# -- 1. every token reaches the JavaScript side ------------------------


def test_the_module_holds_every_token_name_the_surface_exports(loaded: JsRuntime):
    """A name the surface publishes that the module never holds is a
    token no panel can skin from."""
    surface_names = sorted(dss.TOKEN_NAMES)
    module_names = sorted(loaded.json("acervatorTokens.names()"))
    missing = sorted(set(surface_names) - set(module_names))
    extra = sorted(set(module_names) - set(surface_names))
    assert not missing, (
        f"{len(missing)} of {len(surface_names)} surface tokens never "
        f"reached the module: {missing[:10]}"
    )
    assert (
        not extra
    ), f"the module holds {len(extra)} names the surface has no value for: {extra[:10]}"
    assert len(module_names) == len(surface_names) == len(set(surface_names))


def test_the_reach_check_names_a_token_only_the_surface_holds(js: JsRuntime):
    """The control for the check above, on the surface side. Without it a
    module that dropped a token would read as agreement."""
    payload = bridge_payload()
    dropped = dss.TOKEN_NAMES[0]
    del payload["tokens"][dropped]
    js.push(payload)
    module_names = set(js.json("acervatorTokens.names()"))
    missing = set(dss.TOKEN_NAMES) - module_names
    assert missing == {dropped}, f"the check did not name the dropped token: {missing}"


def test_the_reach_check_names_a_token_only_the_module_holds(js: JsRuntime):
    """The control for the check above, on the module side."""
    payload = bridge_payload()
    payload["tokens"]["PLANTED_ONLY_IN_JS"] = "planted"
    js.push(payload)
    module_names = set(js.json("acervatorTokens.names()"))
    extra = module_names - set(dss.TOKEN_NAMES)
    assert extra == {
        "PLANTED_ONLY_IN_JS"
    }, f"the check did not name the planted token: {extra}"


def test_the_module_holds_every_group_the_surface_exports(loaded: JsRuntime):
    """A group the surface publishes that the module cannot answer for."""
    surface_groups = sorted(dss.GROUP_NAMES)
    module_groups = sorted(loaded.json("acervatorTokens.groupNames()"))
    assert module_groups == surface_groups, (
        f"group names disagree: surface {len(surface_groups)}, "
        f"module {len(module_groups)}"
    )


# -- 2. no token value is written in the JavaScript --------------------


@pytest.fixture(scope="module")
def module_source() -> str:
    return MODULE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def module_literals(module_source: str) -> dict:
    return js_literals(module_source)


def test_the_module_writes_no_number(module_literals: dict):
    """A size, a spacing step or a duration typed here is a second source
    of truth for a value the surface already owns."""
    assert not module_literals["numbers"], (
        "design_tokens.js holds numeric literals: " f"{module_literals['numbers']}"
    )


def test_the_module_writes_no_colour(module_source: str):
    """A colour typed here drifts from the surface the next time a theme
    changes, and nothing reports the drift."""
    found = HEX_COLOUR.findall(module_source)
    assert not found, f"design_tokens.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_token_value(module_literals: dict):
    """A token value spelled out as text, colour or not."""
    values = {str(value) for value in dss.TOKENS.values()}
    written = sorted(set(module_literals["strings"]) & values)
    assert not written, f"design_tokens.js spells out token values: {written}"


def test_the_module_hides_no_value_behind_a_regular_expression(module_literals: dict):
    """The scan above parses no regular expression, so a value inside one
    would pass unread. The module carries none."""
    assert not module_literals["slashes"], (
        "design_tokens.js holds a slash outside a comment, which the "
        f"literal scan cannot read: {module_literals['slashes']}"
    )


PLANTED_SOURCES = {
    "colour": 'var x = "#00ffcc";',
    "number": "var x = 12;",
    "token_value": 'var x = "' + dss.PRIMARY + '";',
    "regex": "var x = /ab+c/;",
}


def test_the_literal_scan_names_a_planted_colour():
    """The control for the colour check. A blind scan reports nothing on
    a file that spells a colour out."""
    planted = PLANTED_SOURCES["colour"]
    assert HEX_COLOUR.findall(planted) == ["#00ffcc"]
    assert "#00ffcc" in js_literals(planted)["strings"]


def test_the_literal_scan_names_a_planted_number():
    """The control for the number check."""
    assert js_literals(PLANTED_SOURCES["number"])["numbers"] == ["12"]


def test_the_literal_scan_names_a_planted_token_value():
    """The control for the token-value check."""
    values = {str(value) for value in dss.TOKENS.values()}
    strings = set(js_literals(PLANTED_SOURCES["token_value"])["strings"])
    assert strings & values == {dss.PRIMARY}


def test_the_literal_scan_names_a_regular_expression():
    """The control for the slash check."""
    assert js_literals(PLANTED_SOURCES["regex"])["slashes"]


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    """A scan that treated comments as code would report a false colour,
    and a scan that stopped at one would miss the code after it."""
    source = '// #00ffcc\nvar x = "kept";'
    found = js_literals(source)
    assert found["strings"] == ["kept"]
    assert not found["numbers"]


# -- 4. both sides agree, value for value ------------------------------


def test_every_token_value_agrees_between_the_surface_and_the_module(
    loaded: JsRuntime,
):
    """The whole claim of this unit. A single disagreement means a panel
    skinned from the module does not match the surface."""
    expected = bridge_payload()["tokens"]
    actual = loaded.json(
        "acervatorTokens.names().reduce(function (out, n) {"
        " out[n] = acervatorTokens.token(n); return out; }, {})"
    )
    differing = {
        name: (expected[name], actual.get(name))
        for name in expected
        if actual.get(name) != expected[name]
    }
    assert (
        not differing
    ), f"{len(differing)} of {len(expected)} values differ: {differing}"
    assert len(actual) == len(expected) == len(dss.TOKEN_NAMES)


def test_the_value_check_names_a_changed_value(js: JsRuntime):
    """The control. Two real payloads that differ by one value must not
    compare equal."""
    payload = bridge_payload()
    changed = dss.TOKEN_NAMES[0]
    payload["tokens"][changed] = payload["tokens"][changed] + "0"
    js.push(payload)
    expected = bridge_payload()["tokens"]
    actual = js.json(
        "acervatorTokens.names().reduce(function (out, n) {"
        " out[n] = acervatorTokens.token(n); return out; }, {})"
    )
    differing = [name for name in expected if actual.get(name) != expected[name]]
    assert differing == [
        changed
    ], f"the check did not name the changed value: {differing}"


def test_every_group_holds_the_same_members_on_both_sides(loaded: JsRuntime):
    """A group is how a panel asks for one family of tokens at a time."""
    expected = bridge_payload()["groups"]
    for group, members in expected.items():
        loaded.bind_json("GROUP", group)
        actual = loaded.json("acervatorTokens.group(JSON.parse(GROUP))")
        assert actual == members, f"group {group} disagrees"


def test_every_alias_points_at_the_same_token_on_both_sides(loaded: JsRuntime):
    """A second name for a colour must resolve where the surface says."""
    for name, target in dss.ALIAS_TARGETS.items():
        loaded.bind_json("ALIAS", name)
        assert loaded.json("acervatorTokens.aliasTarget(JSON.parse(ALIAS))") == target


def test_every_value_arrives_as_the_type_the_surface_holds(loaded: JsRuntime):
    """A value that changes shape in transit reads correct and skins
    wrong -- a number where a colour belongs paints nothing."""
    expected = {
        name: JS_TYPE_OF[type(value).__name__] for name, value in dss.TOKENS.items()
    }
    actual = loaded.json("acervatorTokens.types()")
    differing = {
        name: (kind, actual.get(name))
        for name, kind in expected.items()
        if actual.get(name) != kind
    }
    assert not differing, f"{len(differing)} values changed type: {differing}"


def test_the_module_reports_only_what_it_was_given(js: JsRuntime):
    """Every value comes from the payload and none from the module. A
    payload of values the surface never held must come back unchanged."""
    invented = {name: "given-" + name for name in dss.TOKEN_NAMES}
    js.push({"token_names": list(dss.TOKEN_NAMES), "tokens": invented})
    actual = js.json(
        "acervatorTokens.names().reduce(function (out, n) {"
        " out[n] = acervatorTokens.token(n); return out; }, {})"
    )
    assert actual == invented
    real = set(str(value) for value in dss.TOKENS.values())
    assert not set(actual.values()) & real


# -- the bridge ask ----------------------------------------------------


BRIDGE_STUB = (
    "window.CALLS = [];"
    "window.acervator = { call: function (method, params) {"
    "  window.CALLS.push([method, JSON.stringify(params)]);"
    "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
)


def test_the_module_asks_the_backend_for_the_surface_method(js: JsRuntime):
    """The module reaches Python the one way the page allows: the preload
    bridge, naming the method the surface registers."""
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadTokens();")
    drain_events()
    assert js.json("window.CALLS") == [[dss.METHOD, "{}"]]
    assert js.json("acervatorTokens.isLoaded()") is True
    assert len(js.json("acervatorTokens.names()")) == len(dss.TOKEN_NAMES)


def test_a_second_ask_costs_no_second_round_trip(js: JsRuntime):
    """Several panels on one page share one answer."""
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadTokens(); acervatorLoadTokens(); acervatorLoadTokens();")
    drain_events()
    assert len(js.json("window.CALLS")) == 1


def test_the_ask_counter_reports_a_second_round_trip(js: JsRuntime):
    """The control for the check above. A counter that never incremented
    would report one call however many were made."""
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadTokens();")
    drain_events()
    js.run("acervatorTokens.forget(); acervatorLoadTokens();")
    drain_events()
    assert len(js.json("window.CALLS")) == 2


def test_the_module_reports_a_missing_bridge_rather_than_raising(js: JsRuntime):
    """A page opened without the preload script must say so, not draw a
    half-skinned panel."""
    js.run("acervatorLoadTokens();")
    drain_events()
    assert js.json("acervatorTokens.isLoaded()") is False
    assert js.json("acervatorTokens.loadError()") == "the preload bridge is not present"


def test_a_refused_ask_is_not_remembered(js: JsRuntime):
    """A backend that was not running when the page opened must be
    reachable on the next ask, not blanked for the life of the page."""
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(
        "window.TRIES = 0;"
        "window.acervator = { call: function () {"
        "  window.TRIES += 1;"
        "  if (window.TRIES === 1) {"
        "    return Promise.reject(new Error('the Python backend is not running')); }"
        "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
        "acervatorLoadTokens();"
    )
    drain_events()
    assert js.json("acervatorTokens.isLoaded()") is False
    js.run("acervatorLoadTokens();")
    drain_events()
    assert js.json("window.TRIES") == 2
    assert js.json("acervatorTokens.isLoaded()") is True
    assert len(js.json("acervatorTokens.names()")) == len(dss.TOKEN_NAMES)


def test_a_name_the_payload_never_carried_is_not_a_token(js: JsRuntime):
    """Every JavaScript object inherits names like ``constructor`` and
    ``toString``. Reading one as a token would hand a panel a function
    where a colour belongs."""
    js.push(bridge_payload())
    for inherited in ("constructor", "toString", "hasOwnProperty", "valueOf"):
        js.bind_json("NAME", inherited)
        assert js.json("acervatorTokens.has(JSON.parse(NAME))") is False
        assert js.json("acervatorTokens.group(JSON.parse(NAME))") == {}
        # The type, not the value: JSON.stringify turns a function into
        # `undefined`, which is also what an absent token gives.
        for reader in ("token", "aliasTarget"):
            kind = js.json("typeof acervatorTokens." + reader + "(JSON.parse(NAME))")
            assert kind == "undefined", f"{reader}({inherited}) returned a {kind}"


def test_the_inherited_name_check_still_reads_a_real_token(js: JsRuntime):
    """The control for the check above. A reader that answered nothing
    for every name would pass it while serving no token at all."""
    js.push(bridge_payload())
    assert js.json("acervatorTokens.token('SURFACE_0')") == dss.SURFACE_0
    assert js.json("acervatorTokens.aliasTarget('BG')") == "SURFACE_0"
    assert js.json("acervatorTokens.group('colors')") != {}


def test_the_module_reports_a_backend_refusal(js: JsRuntime):
    """The bridge rejects when the Python child is not running."""
    js.run(
        "window.acervator = { call: function () {"
        "  return Promise.reject(new Error('the Python backend is not running')); } };"
        "acervatorLoadTokens();"
    )
    drain_events()
    assert js.json("acervatorTokens.isLoaded()") is False
    assert js.json("acervatorTokens.loadError()") == "the Python backend is not running"


# -- 5. hostile values -------------------------------------------------


def hostile_payload() -> dict:
    """One payload carrying each of the four damaged values at once."""
    payload = bridge_payload()
    del payload["tokens"]["SURFACE_0"]
    payload["tokens"]["TEXT_HIGH"] = None
    payload["tokens"]["PRIMARY"] = 7
    payload["tokens"]["SPACE_M"] = "16"
    return payload


def test_a_declared_token_the_payload_omits_is_named_as_missing(js: JsRuntime):
    """The surface promised the name and sent no value."""
    report = js.push(hostile_payload())
    assert {"name": "SURFACE_0", "fault": "missing"} in report["faults"]
    assert js.json("acervatorTokens.has('SURFACE_0')") is False
    assert js.json("acervatorTokens.token('SURFACE_0')") is None


def test_a_missing_token_shortens_the_held_count_not_the_declared_count(
    js: JsRuntime,
):
    """The two counts are kept apart so a payload that declares more than
    it carries reads as a difference, never as a full table."""
    report = js.push(hostile_payload())
    assert report["declared"] == len(dss.TOKEN_NAMES)
    assert report["held"] == len(dss.TOKEN_NAMES) - 1


def test_a_null_token_is_named_and_left_as_it_arrived(js: JsRuntime):
    """A null is reported, not swapped for a colour of the module's own."""
    report = js.push(hostile_payload())
    assert {"name": "TEXT_HIGH", "fault": "null"} in report["faults"]
    assert js.json("acervatorTokens.has('TEXT_HIGH')") is True
    assert js.json("acervatorTokens.token('TEXT_HIGH')") is None
    assert js.json("acervatorTokens.types()")["TEXT_HIGH"] == "null"


def test_a_number_where_a_colour_belongs_is_reported_not_repaired(js: JsRuntime):
    """The module holds no idea of what type a token should be, so it
    passes the number on and names the type it received."""
    js.push(hostile_payload())
    assert js.json("acervatorTokens.token('PRIMARY')") == 7
    assert js.json("acervatorTokens.types()")["PRIMARY"] == "number"
    assert js.json("acervatorTokens.faults()") == [
        {"name": "SURFACE_0", "fault": "missing"},
        {"name": "TEXT_HIGH", "fault": "null"},
    ]


def test_text_where_a_number_belongs_is_reported_not_repaired(js: JsRuntime):
    """The same the other way. A spacing step sent as text stays text."""
    js.push(hostile_payload())
    assert js.json("acervatorTokens.token('SPACE_M')") == "16"
    assert js.json("acervatorTokens.types()")["SPACE_M"] == "string"


def test_the_type_check_names_all_four_damaged_values(js: JsRuntime):
    """The control for the four checks above, read against the surface's
    own types. A check blind to shape would report agreement here."""
    js.push(hostile_payload())
    expected = {
        name: JS_TYPE_OF[type(value).__name__] for name, value in dss.TOKENS.items()
    }
    actual = js.json("acervatorTokens.types()")
    differing = sorted(
        name
        for name, kind in expected.items()
        if name in actual and actual[name] != kind
    )
    assert differing == ["PRIMARY", "SPACE_M", "TEXT_HIGH"]
    assert "SURFACE_0" not in actual


def test_a_payload_that_is_not_an_object_leaves_the_module_unloaded(js: JsRuntime):
    """A bridge answering with a string or a number draws nothing rather
    than a table of undefined values."""
    for wrong in ("a string", 7, None, ["a", "list"]):
        js.push(wrong)
        assert js.json("acervatorTokens.isLoaded()") is False
        assert js.json("acervatorTokens.names()") == []
        assert js.json("acervatorTokens.faults()") == [
            {"name": "tokens", "fault": "not-an-object"}
        ]


# -- 3. the module under the page's own policy -------------------------


class Browser:
    """The real renderer page, loaded from disk in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtCore import QEventLoop, QTimer, QUrl
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        loop = QEventLoop()
        box: dict = {}

        def _loaded(ok: bool) -> None:
            box.setdefault("ok", ok)
            loop.quit()

        self._view.loadFinished.connect(_loaded)
        self._view.load(QUrl.fromLocalFile(str(INDEX_HTML)))
        QTimer.singleShot(JS_TIMEOUT_MS, loop.quit)
        loop.exec()
        assert box.get("ok") is True, f"{INDEX_HTML.name} did not load: {box}"

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


WATCH_VIOLATIONS = (
    "window.VIOLATIONS = [];"
    "document.addEventListener('securitypolicyviolation', function (e) {"
    "  window.VIOLATIONS.push(e.violatedDirective + ' ' + e.blockedURI); });"
)


def test_the_page_carries_the_policy_the_module_runs_under(browser: Browser):
    """The policy is read off the loaded document, not off the file, so
    what follows is measured against what Chromium applied."""
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert "script-src 'self'" in policy


def test_the_module_loads_under_the_page_policy(browser: Browser):
    """``script-src 'self'`` admits the module. A policy that refused it
    would leave the page with no token API at all."""
    assert browser.js("typeof window.acervatorTokens") == "object"
    assert browser.js("typeof window.acervatorSetTokens") == "function"
    assert browser.js("typeof window.acervatorLoadTokens") == "function"


def test_the_policy_refuses_a_network_call_from_the_loaded_page(browser: Browser):
    """The control for the two checks above. It names the directive that
    refused, which a failed address lookup could not produce."""
    browser.js(
        WATCH_VIOLATIONS + "window.PROBE = 'pending';"
        "fetch('https://example.invalid/x')"
        "  .then(function () { window.PROBE = 'allowed'; })"
        "  .catch(function (e) { window.PROBE = 'refused: ' + e.name; });"
    )
    browser.settle(1500)
    assert browser.js("window.PROBE") == "refused: TypeError"
    violations = json.loads(browser.js("JSON.stringify(window.VIOLATIONS)"))
    assert any(v.startswith("connect-src") for v in violations), violations


def test_the_module_makes_no_network_call_of_its_own(browser: Browser):
    """Driving the whole module raises no policy violation, so nothing in
    it reaches for the network."""
    browser.js(WATCH_VIOLATIONS)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(bridge_payload())) + ";")
    browser.js(
        "acervatorSetTokens(JSON.parse(window.PAYLOAD));"
        "acervatorTokens.apply(document.documentElement);"
    )
    browser.settle(500)
    assert json.loads(browser.js("JSON.stringify(window.VIOLATIONS)")) == []


def test_every_scalar_token_lands_on_the_page_as_a_css_variable(browser: Browser):
    """What a stylesheet actually reads. The value is taken back off the
    rendered document, not off the object that wrote it."""
    payload = bridge_payload()
    expected = scalar_tokens(payload["tokens"])
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    written = json.loads(
        browser.js(
            "JSON.stringify((function () {"
            "  acervatorSetTokens(JSON.parse(window.PAYLOAD));"
            "  return acervatorTokens.apply(document.documentElement); })())"
        )
    )
    assert sorted(written) == sorted(expected)
    read_back = json.loads(
        browser.js(
            "JSON.stringify((function () {"
            "  var style = getComputedStyle(document.documentElement);"
            "  var out = {};"
            "  " + json.dumps(sorted(expected)) + ".forEach(function (n) {"
            "    out[n] = style.getPropertyValue('--' + n).trim(); });"
            "  return out; })())"
        )
    )
    differing = {
        name: (str(value), read_back.get(name))
        for name, value in expected.items()
        if read_back.get(name) != str(value)
    }
    assert not differing, f"{len(differing)} tokens reached no stylesheet: {differing}"


def test_the_css_variable_check_names_a_changed_value(browser: Browser):
    """The control. A read that returned the same text whatever was
    written would report agreement on a changed colour."""
    payload = bridge_payload()
    payload["tokens"]["SURFACE_0"] = payload["tokens"]["SURFACE_0"] + "0"
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetTokens(JSON.parse(window.PAYLOAD));"
        "acervatorTokens.apply(document.documentElement);"
    )
    read_back = browser.js(
        "getComputedStyle(document.documentElement)"
        ".getPropertyValue('--SURFACE_0').trim()"
    )
    assert read_back == payload["tokens"]["SURFACE_0"]
    assert read_back != dss.SURFACE_0


def test_an_array_token_reaches_no_stylesheet_and_is_not_flattened(browser: Browser):
    """A shadow arrives as three parts. Joining them here would invent a
    separator the surface never chose."""
    payload = bridge_payload()
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    written = json.loads(
        browser.js(
            "JSON.stringify((function () {"
            "  acervatorSetTokens(JSON.parse(window.PAYLOAD));"
            "  return acervatorTokens.apply(document.documentElement); })())"
        )
    )
    for name, value in payload["tokens"].items():
        if isinstance(value, list):
            assert name not in written
            assert (
                browser.js(
                    "getComputedStyle(document.documentElement)"
                    ".getPropertyValue('--" + name + "')"
                ).strip()
                == ""
            )


# -- the page wiring ---------------------------------------------------


DOM_STUB = (
    "var written = {};"
    "window.document = {"
    "  documentElement: { style: { setProperty: function (k, v) {"
    "    written[k] = v; } } },"
    "  getElementById: function () { return { textContent: '', hidden: true }; }"
    "};"
    "var document = window.document;"
)


def test_the_page_boot_asks_for_the_tokens_and_puts_them_on_the_root(js: JsRuntime):
    """The wiring, driven rather than read. ``boot.js`` asks once and
    hands every scalar token to the root element."""
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(DOM_STUB)
    js.run(
        "window.CALLS = [];"
        "window.acervator = { call: function (method) {"
        "  window.CALLS.push(method);"
        "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
        "window.acervatorSetState = function () { return 1; };"
    )
    js.run(BOOT_PATH.read_text(encoding="utf-8"))
    drain_events()
    assert dss.METHOD in js.json("window.CALLS")
    expected = scalar_tokens(bridge_payload()["tokens"])
    on_root = js.json("written")
    assert sorted(on_root) == sorted("--" + name for name in expected)
    assert on_root["--" + "SURFACE_0"] == dss.SURFACE_0


def test_the_boot_wiring_control_reports_an_element_never_written(js: JsRuntime):
    """The control. A recorder that reported a full table whatever
    happened would pass the check above with no tokens applied."""
    js.run(DOM_STUB)
    js.run(
        "window.acervator = { call: function () {"
        "  return Promise.reject(new Error('no backend')); } };"
        "window.acervatorSetState = function () { return 1; };"
    )
    js.run(BOOT_PATH.read_text(encoding="utf-8"))
    drain_events()
    assert js.json("written") == {}
